.. _deploy-central-hub-aws:

##############################
Deploy the Central Hub on AWS
##############################

This is the **self-contained** deployment mode: everything FLIP needs lives in one AWS account, and Terraform
builds the network as well as the services. It is the default mode and the one the open-source project targets.

.. seealso::

   - :ref:`deploy-central-hub` — prerequisites, IAM permissions, service authentication, schema changes and email
     setup, shared by both modes.
   - :doc:`deploy-central-hub-aws-lza` — the platform-managed alternative for a Landing Zone Accelerator estate.

.. contents:: On this page
   :local:
   :depth: 2

************
Architecture
************

The diagrams are generated from the Terraform configuration, so they match what is deployed. The security
controls they implement are on :ref:`security`.

.. figure:: ../assets/generated/central-hub-aws-network.png
   :align: center
   :alt: Users and Trust nodes outside AWS; Route 53, CloudFront, WAF, ACM and the UI bucket at the edge; a
         VPC with a NAT gateway and FL network load balancer in public subnets, and an internal application
         load balancer, three Fargate services, Cloud Map, an SSM bastion and an optional mock Trust in
         private subnets; GHCR reached through the NAT gateway.

   Request and FL paths.

There are **two entry points**, both AWS-managed:

Web and API traffic (browsers and each Trust's ``trust-api``)
   HTTPS through **CloudFront**, which carries a WAF, serves the UI from its bucket and forwards ``/api/*`` to an
   **internal** application load balancer. The ALB has no public address and accepts traffic only from
   CloudFront. CloudFront also strips the hub's internal service key header, so the FL server calls ``flip-api``
   over the hub's internal URL instead.

FL traffic (each Trust's FL client)
   A **public network load balancer** passes the mutual-TLS gRPC stream through untouched to the FL server. A
   layer-7 balancer would terminate the TLS that the FL frameworks authenticate with. Only the registered
   Trusts' public IP addresses are allowed in.

Terraform creates the DNS records for both names in the account's Route 53 hosted zone: the UI/API name
(``ALB_SUBDOMAIN``) and the FL name embedded in the trust kits (``NLB_SUBDOMAIN``).

**Compute is ECS Fargate in private subnets.** ``flip-api``, ``fl-api-net-1`` and ``fl-server-net-1`` run with no
public IPs and find each other through a private DNS namespace (``flip.local``). Container images come from GHCR
through a single NAT gateway. Operators connect through AWS Systems Manager Session Manager to a small bastion;
port 22 is never open.

.. figure:: ../assets/generated/central-hub-aws-data.png
   :align: center
   :alt: The three Fargate services with EFS, RDS Proxy, RDS PostgreSQL and VPC endpoints inside the VPC;
         four S3 buckets; and Cognito, KMS, CloudWatch Logs, SES, Parameter Store and Secrets Manager as
         regional services.

   Data and platform services.

**State lives in managed services:**

- **PostgreSQL (RDS)**, reached through RDS Proxy with a short-lived IAM token per connection. The application
  holds no database password, so rotating the master secret causes no outage.
- **EFS** holds the FL workspaces, certificates and job directories. Each net's participant kits are copied there
  from the kits bucket.
- **Four S3 buckets**, all encrypted with the hub's KMS key: model-file staging and scanned files, FL results,
  bundled apps, and participant kits.
- **Cognito** is the user pool, with TOTP MFA.
- **Secrets Manager** holds the ``FLIP_API`` secret (the AES key and the internal service key); **Parameter
  Store** holds plain configuration read at start-up.
- **SES** sends the application's emails.

VPC endpoints for Secrets Manager, SSM, CloudWatch Logs and S3 keep that traffic off the NAT gateway.

*********************
Full-stack deployment
*********************

*Who: FLIP admin, from a workstation with AWS SSO and GitHub CLI access.*

.. important::

   Two things must exist before the first run:

   - **The Terraform state bucket.** It is not created here; it comes from the ``terraform_ci_bootstrap`` module,
     together with the CI roles and the permissions boundary. In AI Centre's accounts the platform repositories
     apply it. In your own account, apply ``deploy/providers/AWS/ci`` first (see its ``README.md``).
   - **The internal service key** (FL server to hub) in the env file. The AWS Makefile will not run without it.
     Mint it from the repository root:

     .. code-block:: shell

        make generate-internal-service-key ENV_FILE=$(pwd)/.env.<env>

Run the whole pipeline with one target:

.. code-block:: shell

   cd deploy/providers/AWS
   make full-deploy PROD=stag    # staging
   make full-deploy PROD=true    # production

``PROD`` selects the env file: ``stag`` uses ``.env.stag``, ``true`` uses ``.env.production``. Production also
turns on RDS deletion protection and a final snapshot.

``full-deploy`` runs these targets in order:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Target
     - What it does
   * - ``github-login``, ``aws-login``
     - Authenticate the GitHub CLI (for image pulls) and AWS SSO.
   * - ``init``
     - Initialise Terraform with the environment's state backend.
   * - ``import-persistent``
     - Import existing persistent resources (Cognito, S3, secrets) so Terraform does not replace them.
   * - ``generate-internal-service-key``
     - Check the internal service key and its hash are in sync.
   * - ``plan``, ``apply``
     - Apply the infrastructure changes.
   * - ``update-env``
     - Write Terraform outputs back into the env file.
   * - ``ssh-config``
     - Add SSM-based SSH entries to ``~/.ssh/config``.
   * - ``ansible-init``
     - Set up the hub bastion, and Docker, CloudWatch and FL assets on the cloud Trust EC2.
   * - ``deploy-centralhub``
     - Deploy the hub's Fargate services at the tip of the environment's branch, and publish the UI.
   * - ``register-trusts``
     - Register the trust roster on the hub and write each trust's credentials into its kit file.
   * - ``deploy-trust``
     - Deploy the AWS-hosted trust, if any. Skip it when all trusts are on-prem.
   * - ``status``
     - Run the health checks (see `Status check`_).

Each hub deploy pins an immutable image tag (``sha-<short7>``). To undo one, repoint the services at the
previous revision:

.. code-block:: shell

   make rollback-centralhub

.. seealso::

   "Central Hub deploys and rollback" in ``deploy/providers/AWS/README.md`` — tag resolution, the ``TAG=``
   override and production rollout timing.

UI-only deploys
===============

To redeploy just the UI, no Terraform is needed:

.. code-block:: shell

   make deploy-ui PROD=stag

This builds the UI from your working tree, uploads it to S3 and invalidates the CloudFront cache. CloudFront is the
only supported way to serve the UI.

***********************
Step-by-step deployment
***********************

To debug or run selected steps, run the same targets one at a time:

.. code-block:: shell

   export PROD=stag    # or: export PROD=true

   make github-login
   make aws-login
   make init
   make import-persistent
   make generate-internal-service-key
   make plan
   make apply
   make update-env
   make ssh-config
   make ansible-init
   make deploy-centralhub
   make register-trusts
   make deploy-trust KIT=<CODE>
   make status

``register-trusts`` must run after ``deploy-centralhub``, and ``deploy-trust`` after ``register-trusts``.

After ``register-trusts``, fill the rest of each kit file's hub-shared settings from the repository root:

.. code-block:: shell

   make sync-trust-kit KIT=<CODE> PROD=<env>

************
Status check
************

.. code-block:: shell

   make status

This checks Terraform state and outputs, the network, EC2 health, database connectivity, Secrets Manager, S3,
Cognito, containers, the public endpoints, SSH access and CloudWatch logging.

******************
SSH access via SSM
******************

Once ``make ssh-config`` has run, connect directly:

.. code-block:: shell

   ssh flip          # Central Hub
   ssh flip-trust    # cloud trust, if deployed

To open the trust's web UIs (XNAT, Orthanc, API docs, Grafana), forward their ports over SSM:

.. code-block:: shell

   make forward-trust

It prints the local URLs to open in your browser. Press ``Ctrl+C`` to close all forwards.

***************************
Destroy infrastructure
***************************

.. code-block:: shell

   make destroy

.. warning::

   This deletes the environment's infrastructure, including the database. It asks you to type ``yes`` first.
   **Cognito**, **Secrets Manager** and the **S3 buckets** are kept. In production, RDS deletion protection is on
   and a final snapshot is taken before deletion is allowed; staging is disposable.

***************
Troubleshooting
***************

Run ``make status`` first: it checks resource health, network connectivity, endpoints, containers and resource
usage.

.. seealso::

   ``deploy/providers/AWS/TROUBLESHOOTING.md`` — Terraform state drift, ECS service errors, CloudFront cache
   invalidation, RDS connectivity and SSM Session Manager issues.
