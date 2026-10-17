.. _deploy-central-hub:

########################
Deploy the Central Hub
########################

The Central Hub is the cloud-hosted side of FLIP. It manages projects and users, runs the federated learning server
and serves the web UI. It runs on AWS and is provisioned with Terraform (or OpenTofu) from one root module,
``deploy/providers/AWS/``, in one of **two deployment modes**.

This page covers what the two modes share. Each mode has its own page with its architecture and runbook. To deploy a
trust, see :doc:`deploy-flip-node-on-prem` or :doc:`deploy-flip-node-in-tre`.

.. contents:: On this page
   :local:
   :depth: 1

****************
Deployment modes
****************

Both modes are permanently supported and use the same code. You choose one with the ``PROD`` setting, not by
forking anything.

.. list-table::
   :header-rows: 1
   :widths: 20 18 31 31

   * - Mode
     - Selected by
     - Network
     - Ingress
   * - **Self-contained** (default)
     - ``PROD=stag`` / ``PROD=true``
     - FLIP creates its own VPC, subnets, internet gateway and NAT
     - In-account CloudFront for the UI and ``/api/*``; a public NLB for FL traffic
   * - **Platform-managed**
     - ``PROD=lza`` (production) / ``PROD=lza-stag`` (staging)
     - Discovered from a VPC provisioned by the AWS `Landing Zone Accelerator
       <https://aws.amazon.com/solutions/implementations/landing-zone-accelerator-on-aws/>`_;
       FLIP creates no network resources
     - A shared networking account's edge, reached over a Transit Gateway; no public load
       balancer in the workload account

**Self-contained** puts everything in one AWS account. It is the simplest way to stand up a hub and the shape the
open-source project targets. See :doc:`deploy-central-hub-aws`.

**Platform-managed** is for an AWS estate already governed by the Landing Zone Accelerator, where a platform team owns
the network, the guardrails and a shared edge. FLIP uses the network it is given instead of building one, so you must
coordinate with whoever runs the estate. See :doc:`deploy-central-hub-aws-lza`.

.. toctree::
   :maxdepth: 1

   deploy-central-hub-aws
   deploy-central-hub-aws-lza

.. _deploy-central-hub-costs:

*************
Running costs
*************

These are rough figures for the **Central Hub only** (one hub, one FL net). They were measured from the AI Centre's
own bills in September 2026, in ``eu-west-2``, in US dollars before VAT, at on-demand prices. For a budget, use what
Cost Explorer reports for your account.

.. list-table::
   :header-rows: 1
   :widths: 18 44 12 26

   * - Mode
     - What bills to the workload account
     - Roughly
     - Notes
   * - **Self-contained**
     - ECS Fargate (three tasks), RDS and RDS Proxy, EFS, the internal ALB and the public
       FL NLB, a NAT gateway and in-account VPC endpoints, CloudFront and its WAF,
       CloudWatch, GuardDuty and Security Hub
     - $500 a month
     - Fargate is about a third of it; the NAT gateway and endpoints about a fifth.
       Everything is in the one account, so this is the whole bill.
   * - **Platform-managed**
     - The same compute and data services, minus the NAT gateway, endpoints, CloudFront,
       WAF and ALB, which the estate provides centrally
     - $400 a month
     - Plus a share of the **platform layer**: Transit Gateway attachments, the central
       Network Firewall, central endpoints and NAT, and the shared edge. For the AI
       Centre's estate that layer is of the order of $800 a month in total. It exists
       whether or not FLIP is deployed, so attribute all of it to FLIP only when FLIP is
       the estate's sole workload.

The platform-managed hub is not cheaper on its own. It becomes cheaper per workload once the estate hosts several, and
its platform-layer charges land on the platform team's accounts, so agree with them how that cost is recharged.
Staging costs about the same as production in either mode: nothing in the hub scales with the number of users.

.. note::

   **Trust hosts are not included.** A trust's cost depends on its GPU instance and how long that instance is busy,
   which depends on the projects it joins. The mock trust EC2 in the self-contained runbook (a ``t3.xlarge`` with no
   GPU) is a test fixture, not a sizing recommendation. For always-on versus on-demand GPUs, see *GPU Resource
   Management* in :doc:`deploy-flip-node-in-tre`.

Everything below applies to both modes.

*************
Prerequisites
*************

1. **AWS CLI with SSO access**. See `deploy/README.md
   <https://github.com/londonaicentre/FLIP/blob/main/deploy/README.md>`_.
2. **Terraform >= 1.13.1** (or OpenTofu).
3. **Python 3.12 or 3.13** with `UV <https://docs.astral.sh/uv/guides/install-python/>`_.
4. **GitHub CLI**, to authenticate against GitHub Container Registry for image pulls.
5. **An environment file** in the project root for your environment (see the table below).
6. **AWS profiles** in ``~/.aws/config`` named after each environment (see the table below). The Makefile refuses to
   run if the active profile does not match the chosen environment.
7. Self-contained mode only:

   - an **SSH key pair** at ``~/.ssh/host-aws``, uploaded to AWS and used for SSH over SSM;
   - the **AWS Session Manager plugin**, needed for ``ssh flip`` and ``make forward-trust``.

   The platform-managed mode has no SSH or Ansible step.

**Choose the environment with** ``PROD``:

.. list-table::
   :header-rows: 1
   :widths: 18 22 18 18 24

   * - ``PROD``
     - Environment file
     - AWS profile
     - Treated as
     - Mode
   * - ``stag``
     - ``.env.stag``
     - ``stag``
     - staging
     - self-contained
   * - ``true``
     - ``.env.production``
     - ``prod``
     - production
     - self-contained
   * - ``lza-stag``
     - ``.env.lza-stag``
     - ``lza-stag``
     - staging
     - platform-managed
   * - ``lza``
     - ``.env.lza-prod``
     - ``lza-prod``
     - production
     - platform-managed

Production environments get the production-only database safeguards (RDS deletion protection and a final snapshot).
The mode and the environment are independent: ``PROD=lza`` keeps every production control, while ``PROD=lza-stag`` is
staging on the platform-managed network.

************************
Required IAM permissions
************************

The operator role that provisions the infrastructure needs these managed policies, or equivalent custom permissions:

- ``AmazonEC2FullAccess``
- ``AmazonECS_FullAccess``
- ``AmazonRDSFullAccess``
- ``AmazonElasticFileSystemFullAccess``
- ``CloudWatchLogsFullAccess``
- ``SecretsManagerReadWrite``
- ``IAMFullAccess``
- ``ElasticLoadBalancingFullAccess`` (covers ALB and NLB)
- ``CloudFrontFullAccess``
- ``AWSWAFFullAccess``
- ``AWSCertificateManagerFullAccess``
- ``AmazonRoute53FullAccess``
- ``AWSCloudMapFullAccess``
- ``AmazonSSMFullAccess``
- ``AmazonSESFullAccess`` (optional, for email)

The deployed services themselves run with scoped, least-privilege roles, not these broad permissions.

On a **platform-managed** estate, the workload account's Identity Center permission set replaces this list, bounded by
the estate's service control policies. Creating network resources is denied there by design.

.. seealso::

   "Required IAM permissions" in `deploy/providers/AWS/README.md
   <https://github.com/londonaicentre/FLIP/blob/main/deploy/providers/AWS/README.md>`_ holds the canonical list.

***********************
Service authentication
***********************

The hub uses three separate keys. See :doc:`/sys-admin` for full details.

.. list-table::
   :header-rows: 1
   :widths: 22 40 38

   * - Key
     - What it protects
     - How it is created
   * - **Trust API key**
     - Each trust's calls to the hub. One key per trust.
     - Minted when you register the trust and written once into its kit file
       (``trust/.env.<CODE>.<env>``). The hub keeps only a hash.
   * - **Internal service key**
     - Calls from the FL server to the hub API. One key per hub.
     - ``make generate-internal-service-key``
   * - **Trust-internal service key**
     - Calls between services inside one trust. One key per trust; the hub never sees it.
     - Minted alongside the trust API key and written into the trust's kit file.

Generate the internal service key into the active environment file. Existing keys are kept:

.. code-block:: shell

   make generate-internal-service-key

Register trusts from ``deploy/providers/AWS``, one kit at a time or every kit file present for the environment:

.. code-block:: shell

   make register-trusts KIT=<CODE>   # one trust
   make register-trusts              # every trust/.env.*.<env> kit file

**********************************************
Upgrading across the payload-encryption change
**********************************************

Task payloads between the hub and its trusts are encrypted with AES-256-GCM. Releases before this change used
AES-CBC, and the two formats are **not compatible**. A hub and every trust registered to it must upgrade together, in
one maintenance window.

*Who: FLIP admin (hub) and every trust operator*

1. **Pause FL activity.** In the UI, enable Deployment Mode (*Admin → Deployments*). Wait until ``GET /fl/quiesce``
   reports ``deployment_mode: true`` and ``fl_quiesced: true``.
2. **Redeploy the hub and every trust** in the same window: ``make deploy-centralhub`` for the hub, and
   ``make deploy-trust``, the on-prem playbook or the Kubernetes chart for each trust.
3. **Resume.** Disable Deployment Mode.

.. warning::

   Anything still encrypted in the old format when you upgrade fails afterwards. Step 1 prevents this. If it happens:

   - A task a trust collected before it upgraded stays ``IN_PROGRESS``. Reset it to ``PENDING``.
   - A running FL job fails at the trust's imaging service once that trust upgrades.

.. important::

   ``AES_KEY_BASE64`` must be identical on the hub and on every trust. On staging and production, the hub's value is
   the one CI wrote into Secrets Manager, which may differ from your checked-out ``.env.<env>``. Recover the deployed
   value with ``deploy/providers/AWS/scripts/reconcile_ci_env.py``.

***********************
Applying schema changes
***********************

Database migrations apply **automatically**. Every time a ``flip-api`` container starts, it brings the hub database
up to date before serving traffic. If a migration fails, the container refuses to start rather than run against a
schema it does not expect.

- **Development**: ``make restart`` recreates the ``flip-api`` container (``deploy-flip-api-1``), which migrates on
  boot.
- **Staging and production** (either mode): a normal redeploy, ``make deploy-centralhub`` from
  ``deploy/providers/AWS/``, migrates before the new task serves traffic.

Migrations alter the existing tables in place, so your data is preserved. There is **no** drop-and-recreate step for
the hub database in routine operation.

.. note::

   For developers: every change to the hub's database models must ship an Alembic revision in the same PR, and CI
   fails otherwise. How to author and review one is in `flip-api/README.md
   <https://github.com/londonaicentre/FLIP/blob/develop/flip-api/README.md>`_.

**********************************
FL image compatibility on upgrade
**********************************

The hub now **requires** FL clients to identify themselves when they report training metrics and logs. FL images built
before this change do not, so the hub and the FL images (``flare-fl-base`` for NVFLARE, ``flower-fl-base`` for Flower)
must be upgraded together.

.. warning::

   With an old FL image, training appears to complete but the metrics chart and logs stay empty: the hub rejects the
   reports and the client ignores the rejection. Deploy the hub and bump the trust-side FL image tag in the same
   maintenance window, and do not run training in between.

The same release of the ``flip-utils`` package adds the trust-internal service key to the ``flip`` client calls (see
:ref:`trust-internal-service-authentication`).

************
Email setup
************

FLIP sends its own emails through Amazon SES. Before the first deploy:

1. **Verify the sender identity.** Terraform creates the SES identity; click the link in the verification email sent
   to that address.
2. **Check the status.** The identity should show **Verified** in the SES console.

If SES is still in its sandbox, request production access from the SES console. Until then you can only send to
verified addresses.

.. note::

   SES carries only the emails FLIP itself sends: access-request notifications and XNAT credential emails.
   **Cognito sends user invitations and password-reset codes itself**, not through SES. So a broken or sandboxed SES
   identity does not stop invitations or password resets, and fixing SES does not fix them. Cognito's built-in sender
   has its own delivery limits.

.. note::

   Development uses neither service. Emails are written to the ``flip-api`` log instead of being sent, and a local
   Keycloak replaces Cognito for sign-in. The dev Keycloak has no mail server, so a new user gets the shared dev
   password (``ADMIN_USER_PASSWORD``) as a temporary password instead of an invitation. See :doc:`deploy-local-dev`.
