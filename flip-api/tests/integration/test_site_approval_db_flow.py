# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Approval authority is the SITE's decision, checked against real role rows (FLIP#1258).

The primitive (``has_trust_permissions``) is covered in ``test_auth_permissions_db_flow.py``.
What these prove is the *wiring*: that the approval endpoint consults it per named trust, and
that the platform-wide ``CAN_APPROVE_PROJECTS`` grant a Central Hub administrator holds no
longer approves anything. That wiring is the whole substance of #1258 — the machinery already
existed and the endpoint simply never used it, so a hub admin could approve on behalf of every
trust in the federation.

Real Postgres via the shared session fixture, and real ``user_role`` rows: the check walks
``user_role`` → ``role_permission`` → ``permission`` with a scope predicate, which a mocked
session cannot exercise. ``test_has_trust_permissions_ignores_global_admin_grant`` proves the
predicate in isolation; these prove the endpoint reaches it.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import select

from flip_api.db.models.main_models import ProjectTrustIntersect
from flip_api.db.models.user_models import RoleRef, UserRole
from flip_api.domain.schemas.projects import ApproveProjectBodyPayload
from flip_api.domain.schemas.status import ProjectStatus, TrustApprovalStatus
from flip_api.project_services.approve_project import approve_project_endpoint


@pytest.fixture
def staged_project(session, user_factory, project_factory, trust_factory, project_trust_intersect_factory):
    """A STAGED project with two pending intersects — the precondition for approval.

    Built here rather than imported from ``test_project_db_flow``, whose fixture is local to
    that module; duplicating six lines beats coupling two files' fixtures together.
    """
    owner = user_factory()
    project = project_factory.build(owner_id=owner.id, status=ProjectStatus.STAGED, deleted=False)
    trusts = [trust_factory.build(), trust_factory.build()]

    session.add(project)
    for trust in trusts:
        session.add(trust)
    session.flush()
    for trust in trusts:
        session.add(project_trust_intersect_factory.build(
                project_id=project.id, trust_id=trust.id, status=TrustApprovalStatus.PENDING
            ))
    session.commit()

    return {"project": project, "trusts": trusts}


def _payload(trusts, declined=()) -> ApproveProjectBodyPayload:
    return ApproveProjectBodyPayload(trusts=[t.id for t in trusts], declined=[t.id for t in declined])


def _decisions(session, project) -> dict:
    rows = session.exec(
        select(ProjectTrustIntersect)
        .where(ProjectTrustIntersect.project_id == project.id)
        .execution_options(populate_existing=True)
    ).all()
    return {row.trust_id: row for row in rows}


def _grant(user_id, role, trust_id=None):
    return UserRole(user_id=user_id, role_id=role.value, trust_id=trust_id)


def test_hub_admin_global_grant_cannot_approve(session, staged_project):
    """The #1258 regression: a platform-wide Admin grant approves NOTHING.

    Before this change the endpoint accepted ``CAN_APPROVE_PROJECTS``, which Admin holds
    globally — so a Central Hub administrator could approve every trust's participation,
    deciding what each site released. Admin is seeded with all *global* permissions and
    deliberately not with the trust-scoped ones, so this must now be refused.
    """
    admin_id = uuid4()
    session.add(_grant(admin_id, RoleRef.ADMIN))
    session.commit()
    project = staged_project["project"]

    with pytest.raises(HTTPException) as exc_info:
        approve_project_endpoint(
            project_id=project.id,
            payload=_payload(staged_project["trusts"]),
            user_id=admin_id,
            db=session,
        )

    assert exc_info.value.status_code == 403
    # And nothing was approved: the refusal precedes the write.
    session.refresh(project)
    assert project.status == ProjectStatus.STAGED


def test_trust_owner_approves_at_their_own_trust(session, staged_project):
    """A Trust Owner may approve for the trust they own — the point of the change.

    The other trust is still pending, so the decision is recorded and the project stays STAGED (FLIP#1318).
    """
    owner_id = uuid4()
    own_trust, other = staged_project["trusts"]
    session.add(_grant(owner_id, RoleRef.TRUST_OWNER, trust_id=own_trust.id))
    session.commit()
    project = staged_project["project"]

    result = approve_project_endpoint(
        project_id=project.id,
        payload=_payload([own_trust]),
        user_id=owner_id,
        db=session,
    )

    assert result == []
    decisions = _decisions(session, project)
    assert decisions[own_trust.id].status == TrustApprovalStatus.APPROVED
    assert decisions[own_trust.id].decided_by == owner_id
    assert decisions[other.id].status == TrustApprovalStatus.PENDING
    session.refresh(project)
    assert project.status == ProjectStatus.STAGED


def test_each_trust_owner_decides_for_their_own_trust_and_the_last_approves_the_project(session, staged_project):
    """Two sites, two owners, two calls: the second approves the project and gets BOTH trusts back.

    The first trust comes back although the second owner holds no authority there — its own owner's recorded
    approval is what authorised it, so the imaging fan-out must dispatch to it without re-checking the caller.
    """
    first, second = staged_project["trusts"]
    first_owner, second_owner = uuid4(), uuid4()
    session.add(_grant(first_owner, RoleRef.TRUST_OWNER, trust_id=first.id))
    session.add(_grant(second_owner, RoleRef.TRUST_OWNER, trust_id=second.id))
    session.commit()
    project = staged_project["project"]

    assert approve_project_endpoint(project.id, _payload([first]), first_owner, session) == []
    result = approve_project_endpoint(project.id, _payload([second]), second_owner, session)

    assert {trust.id for trust in result} == {first.id, second.id}
    decisions = _decisions(session, project)
    assert decisions[first.id].decided_by == first_owner
    assert decisions[second.id].decided_by == second_owner
    session.refresh(project)
    assert project.status == ProjectStatus.APPROVED


def test_trust_owner_declines_at_their_own_trust(session, staged_project):
    """Declining is the site's decision too, taken on the same grant."""
    owner_id = uuid4()
    own_trust, _other = staged_project["trusts"]
    session.add(_grant(owner_id, RoleRef.TRUST_OWNER, trust_id=own_trust.id))
    session.commit()
    project = staged_project["project"]

    assert approve_project_endpoint(project.id, _payload([], declined=[own_trust]), owner_id, session) == []

    decisions = _decisions(session, project)
    assert decisions[own_trust.id].status == TrustApprovalStatus.DECLINED
    assert decisions[own_trust.id].decided_by == owner_id


def test_trust_owner_cannot_decline_at_a_trust_they_do_not_own(session, staged_project):
    """A decline at a trust the caller does not own is refused like an approval, and nothing is recorded."""
    owner_id = uuid4()
    owned, not_owned = staged_project["trusts"]
    session.add(_grant(owner_id, RoleRef.TRUST_OWNER, trust_id=owned.id))
    session.commit()
    project = staged_project["project"]

    with pytest.raises(HTTPException) as exc_info:
        approve_project_endpoint(project.id, _payload([owned], declined=[not_owned]), owner_id, session)

    assert exc_info.value.status_code == 403
    decisions = _decisions(session, project)
    assert {row.status for row in decisions.values()} == {TrustApprovalStatus.PENDING}


def test_trust_owner_cannot_approve_at_a_trust_they_do_not_own(session, staged_project):
    """Authority at trust A says nothing about trust B — the scope predicate, through the endpoint."""
    owner_id = uuid4()
    owned, not_owned = staged_project["trusts"]
    session.add(_grant(owner_id, RoleRef.TRUST_OWNER, trust_id=owned.id))
    session.commit()
    project = staged_project["project"]

    with pytest.raises(HTTPException) as exc_info:
        approve_project_endpoint(
            project_id=project.id,
            payload=_payload([not_owned]),
            user_id=owner_id,
            db=session,
        )

    assert exc_info.value.status_code == 403
    session.refresh(project)
    assert project.status == ProjectStatus.STAGED


def test_owner_of_one_trust_cannot_approve_a_list_naming_two(session, staged_project):
    """Authority at one of two named trusts refuses the WHOLE call — no partial writes.

    Approving the first trust and refusing the second would return an error after having
    written something, which is the failure the all-or-nothing check exists to prevent.
    """
    owner_id = uuid4()
    first, second = staged_project["trusts"]
    session.add(_grant(owner_id, RoleRef.TRUST_OWNER, trust_id=first.id))
    session.commit()
    project = staged_project["project"]

    with pytest.raises(HTTPException) as exc_info:
        approve_project_endpoint(
            project_id=project.id,
            payload=_payload([first, second]),
            user_id=owner_id,
            db=session,
        )

    assert exc_info.value.status_code == 403
    session.refresh(project)
    assert project.status == ProjectStatus.STAGED, "no partial approval may have been committed"


def test_trust_owner_role_granted_globally_confers_no_per_trust_authority(session, staged_project):
    """``trust_id IS NULL`` never satisfies a trust-scoped check, even for the right role.

    The Trust Owner role carries ``CAN_APPROVE_FOR_TRUST``, so a row that names the role but
    no trust is the one shape which could plausibly be misread as "may approve anywhere". It
    must not be: authority is per trust, and a global row carries none. The seeder never
    writes this shape and ``set_user_roles`` refuses to grant TRUST_OWNER without a trust —
    this pins the check itself, which is what actually stands between the two.
    """
    user_id = uuid4()
    session.add(_grant(user_id, RoleRef.TRUST_OWNER, trust_id=None))
    session.commit()
    project = staged_project["project"]

    with pytest.raises(HTTPException) as exc_info:
        approve_project_endpoint(
            project_id=project.id,
            payload=_payload([staged_project["trusts"][0]]),
            user_id=user_id,
            db=session,
        )

    assert exc_info.value.status_code == 403
    session.refresh(project)
    assert project.status == ProjectStatus.STAGED
