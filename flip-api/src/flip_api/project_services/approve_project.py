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

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from sqlmodel import Session

from flip_api.auth.auth_utils import has_permissions
from flip_api.auth.dependencies import verify_token
from flip_api.db.database import get_session
from flip_api.db.models.main_models import Projects
from flip_api.db.models.user_models import PermissionRef
from flip_api.domain.interfaces.project import IProjectApproval
from flip_api.domain.interfaces.trust import ITrust
from flip_api.domain.schemas.projects import ApproveProjectBodyPayload
from flip_api.domain.schemas.status import ProjectStatus
from flip_api.project_services.services.project_services import (
    InvalidTrustDecisionsError,
    ProjectNotStagedError,
    record_trust_decisions,
)
from flip_api.trusts_services.services.trust import get_trusts
from flip_api.utils.logger import logger

router = APIRouter(prefix="/projects", tags=["project_services"])


# TODO [#114] This endpoint was not defined in the old repo. It was used as a step of a 'approveProject' step function.
@router.post(
    "/{project_id}/approve",
    summary="Record trust decisions on a staged project, approving it once every trust is decided and one approved.",
    response_model=list[ITrust],
    status_code=status.HTTP_200_OK,
)
def approve_project_endpoint(
    project_id: UUID = Path(..., description="The ID of the project to decide on."),
    payload: ApproveProjectBodyPayload = Body(
        ..., description="Payload containing the trust IDs to approve the project for and those that decline it."
    ),
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_session),
) -> list[ITrust]:
    """
    Records trust decisions on a project that is currently in the 'STAGED' status.
    The trusts in ``trusts`` approve the project and those in ``declined`` decline it; any trust named in neither
    keeps its current decision. The project is approved once no trust is pending and at least one approved; if
    every trust declined it stays STAGED.

    Args:
        project_id (UUID): The ID of the project to decide on.
        payload (ApproveProjectBodyPayload): The trust IDs that approve the project and those that decline it.
        user_id (UUID): The ID of the user making the request.
        db (Session): The database session.

    Returns:
        list[ITrust]: Every approved trust if this call approved the project, otherwise an empty list (the project
        is still STAGED).

    Raises:
        HTTPException: If the user does not have permission to approve projects, if the project does not exist,
                       or if there are validation errors.
    """
    logger.debug(f"Attempting to approve project: {project_id} by user: {user_id}")

    # 1. Check user permissions
    if not has_permissions(user_id, [PermissionRef.CAN_APPROVE_PROJECTS], db):
        logger.error(f"User {user_id} does not have permission to approve project {project_id}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User with ID: {user_id} was unable to approve this project",
        )

    # Schema validation
    trust_ids = payload.trusts

    project_approval = IProjectApproval(
        project_id=project_id,
        trust_ids=trust_ids,
        declined_trust_ids=payload.declined,
    )

    # 2. Check if project exists
    project = db.get(Projects, project_id)
    if not project:
        logger.error(f"Project with ID {project_id} not found for approval.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project ID: {str(project_id)} does not exist",
        )

    # 3. Validate whether project has STAGED status
    if not project.status == ProjectStatus.STAGED:
        logger.error(f"Project {project_id} is not in STAGED status, cannot approve.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to approve the project as it has not been staged",
        )

    try:
        try:
            outcome = record_trust_decisions(db, project_approval, user_id)
        except ProjectNotStagedError:
            # Another approver approved the project between the check above and taking the project lock.
            logger.error(f"Project {project_id} left STAGED before its trust decisions were recorded.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to approve the project as it has not been staged",
            )
        except InvalidTrustDecisionsError as e:
            logger.error(f"Rejected trust decisions on project {project_id}: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # get_trusts with no ids returns every trust, so an empty list must never reach it.
        if outcome.project_status != ProjectStatus.APPROVED or not outcome.approved_trust_ids:
            logger.info(f"Project {project_id} stays STAGED: a trust is still pending, or every trust declined")
            return []

        logger.debug(f"Fetching endpoints for approved trusts: {outcome.approved_trust_ids} for project {project_id}")
        return get_trusts(db, ids=outcome.approved_trust_ids)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Unhandled error during project approval for {project_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e
