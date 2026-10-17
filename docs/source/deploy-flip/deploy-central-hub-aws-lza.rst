.. _deploy-central-hub-aws-lza:

####################################
Deploy the Central Hub on AWS (LZA)
####################################

This is the **platform-managed** deployment mode, for an AWS estate governed by the
`Landing Zone Accelerator <https://aws.amazon.com/solutions/implementations/landing-zone-accelerator-on-aws/>`_
(LZA). A platform team owns the network, the guardrails and a shared edge, and FLIP's workload account is not
allowed to create network resources.

It uses the same Terraform as the self-contained mode, selected with ``PROD=lza`` (production) or
``PROD=lza-stag`` (staging). Self-contained environments are unaffected by this mode.

This page explains **what the mode changes and what the estate must provide**.

.. seealso::

   - `Deploying onto an LZA estate
     <https://github.com/londonaicentre/FLIP/blob/main/deploy/providers/AWS/README.md#deploying-onto-an-lza-estate-prodlza>`_
     in ``deploy/providers/AWS/README.md`` — the operator runbook: the env file, the out-of-band prerequisites and
     their commands, and the apply sequence.
   - :ref:`deploy-central-hub` — prerequisites, IAM permissions, service authentication, schema changes and email
     setup, shared with the self-contained mode.

.. contents:: On this page
   :local:
   :depth: 2

************
Architecture
************

The diagrams are generated from the same source as those on :doc:`deploy-central-hub-aws`, showing only the
resources this mode deploys. The networking account's edge and the Transit Gateway belong to the platform team and
are drawn from the handoff contract, not from FLIP's Terraform.

.. figure:: ../assets/generated/central-hub-aws-lza-network.png
   :align: center
   :alt: Users and Trust nodes outside AWS; in the networking account an edge CloudFront with WAF, a web
         relay NLB, an internet-facing edge NLB, and a Network Firewall in front of a Transit Gateway; in
         the workload account the accelerator-provisioned VPC with app subnets holding one internal NLB,
         three Fargate services, Cloud Map, an SSM bastion and an optional mock Trust, a private hosted
         zone, the UI bucket, the SSM handoff parameters and an ECR pull-through cache reaching GHCR.

   Request and FL paths on an LZA estate.

**The front door is in the estate's networking account**, run by the platform team:

Web and API traffic (browsers and each Trust's ``trust-api``)
   HTTPS through a **CloudFront** distribution with a WAF. It serves the UI from FLIP's bucket and forwards
   ``/api/*`` through a relay load balancer in the networking account.

FL traffic (each Trust's FL client)
   An internet-facing **edge NLB**, on TCP port **8002 for production** and **8003 for staging** (the two share one
   listener set).

Both paths then cross the estate's **Transit Gateway** and central **Network Firewall** into the workload account.

**One internal NLB receives both.** The workload VPC has no internet gateway or NAT, so nothing in it can be
public. A single internal network load balancer, with a fixed IP address in each subnet (``.251``), forwards
``:443`` to ``flip-api`` and passes ``:8002`` (mutual-TLS gRPC) through untouched to the FL server. Because the
addresses never change, the edge registers them once. A private hosted zone resolves the FL server's name to the
same addresses inside the VPC.

**No internet egress.** Container images come from an in-account **ECR pull-through cache** that mirrors GHCR and
ECR Public, reached over the estate's central ECR endpoints. The platform team's interface endpoints serve Secrets
Manager, Cognito, SES, SSM and CloudWatch Logs. Operators still connect through Session Manager to the bastion;
port 22 is never open.

.. figure:: ../assets/generated/central-hub-aws-lza-data.png
   :align: center
   :alt: The three Fargate services with EFS and RDS Proxy in the app subnets and RDS PostgreSQL in the
         isolated data subnets of the accelerator-provisioned VPC; central interface endpoints in the
         networking account; five S3 buckets; and Cognito, KMS, CloudWatch Logs, SES, Parameter Store,
         Secrets Manager and an ACM certificate as regional services.

   Data and platform services on an LZA estate.

**Data and platform services are the same as in the self-contained mode**, with two placement differences:

- the database sits in the accelerator's isolated **data subnets**, which have only local routes;
- the interface endpoints are the estate's central ones, not resources in FLIP's account.

*********************
What the mode changes
*********************

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - FLIP's Terraform…
     - Resources
   * - **Does not create**
     - - The VPC, subnets, internet gateway, NAT gateways and DHCP options.
       - VPC endpoints (interface endpoints are central; S3 and DynamoDB gateway endpoints come from the platform).
       - CloudFront, its WAF and the public FL NLB. The estate's edge replaces them.
       - The internal ALB. The internal NLB fronts ``flip-api`` instead.
       - The security-group drift monitor. The organisation baseline covers it.
   * - **Discovers**
     - The accelerator-provisioned VPC and every ``app`` and ``data`` subnet, by Name tag (``LZA_VPC_NAME``).
       Subnets the platform team adds later appear on the next plan.
   * - **Keeps unchanged**
     - ECS Fargate, RDS and RDS Proxy, EFS, Cloud Map, Cognito, S3 with the hub's KMS key, Secrets Manager,
       Parameter Store and SES.

Without the ALB, two behaviours change:

- **No path filtering at the load balancer.** It no longer restricts traffic to ``/api`` or answers a default 404.
  CloudFront and the WAF are the only layer-7 gate, so the workload load balancer must stay reachable only from
  the edge.
- **Idle connections time out after 350 seconds**, not 60.

***********************************
What the platform team must provide
***********************************

*Who: the platform team operating the estate.*

.. important::

   Each FLIP environment needs its **own workload account**. Resource names and handoff parameters are fixed per
   account, so two environments cannot share one.

Before the first ``plan``, provide:

- **Network:** a VPC with ``app`` and ``data`` subnets across two availability zones, a Transit Gateway attachment
  spanning both, and a route from the app subnets to the Transit Gateway.
- **Endpoints**, reachable from the app subnets: central interface endpoints for ``ecr.api`` and ``ecr.dkr``,
  Secrets Manager, Cognito, SES, SSM and CloudWatch Logs; plus S3 and DynamoDB gateway endpoints.
- **Edge**, in the networking account: the CloudFront distribution with its relay, the edge NLB with a listener
  port for this environment, and firewall rules admitting the edge's address ranges to the workload load
  balancer's web and FL ports.
- **ECR pull-through cache rules:** ``ghcr/`` (backed by a read-only GHCR token in Secrets Manager) and
  ``ecr-public/``.
- **Terraform CI bootstrap:** the state bucket, the GitHub OIDC provider and the CI plan and apply roles, applied
  from FLIP's ``terraform_ci_bootstrap`` module pinned to a FLIP commit. FLIP's roles carry the accelerator's own
  permissions boundary, ``AICentre-WorkloadRoleBoundary``, which an SCP requires and the LZA modes use by
  default. The module configures the bucket (versioned, public access blocked, TLS only, encrypted).
- **Operator access:** an Identity Center permission set, with a matching ``lza-prod`` or ``lza-stag`` profile in
  the operator's ``~/.aws/config``.
- **Logging:** the estate's central load-balancer access-logs bucket, which the workload stack writes to.

This platform layer (Transit Gateway, central firewall, endpoints, NAT and edge) is a shared cost billed to the
platform team's accounts, not the workload account. :ref:`deploy-central-hub-costs` gives its rough size.

**********************
Two-phase edge handoff
**********************

The edge is built from the workload stack's outputs, so the two are always applied in this order:

1. **Apply the workload stack.** *Who: FLIP admin (or CI).*

   The first ``apply`` publishes the handoff parameters under ``/flip/networking/*``: the internal NLB's fixed IP
   addresses, the web and FL ports, and its DNS name. Leave ``TF_VAR_lza_web_edge_domain`` and
   ``TF_VAR_lza_web_edge_distribution_arn`` empty. Until they are set, the UI bucket grants no one access and the UI
   origin is a placeholder.

2. **Apply the edge.** *Who: platform team.*

   The edge stack in the networking account reads the handoff parameters.

3. **Point the workload stack at the edge.** *Who: FLIP admin (or CI).*

   Set the two variables to the edge distribution's domain and ARN in the env file, then apply again. This grants
   the edge read access to the UI bucket and points bucket CORS and the Cognito callback URLs at the edge.

Later changes to the workload load balancer follow the same order, networking stack first.

*********
Deploying
*********

**CI applies this estate**, authenticated by GitHub OIDC with no long-lived AWS keys:

- every pull request into ``main`` or ``develop`` that touches ``deploy/providers/AWS/**`` plans LZA staging;
- a push to ``develop`` applies LZA staging;
- a merge to ``main`` applies **LZA production**;
- a nightly plan reports drift.

To point a GitHub environment at another account, change its values (the ``TF_PROD`` mode and the two role ARNs);
see "Repointing CI at the LZA accounts" in the deployment README.

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Setting
     - ``PROD=lza``
     - ``PROD=lza-stag``
   * - Env file
     - ``.env.lza-prod``
     - ``.env.lza-stag``
   * - Semantics
     - Production (RDS deletion protection and final snapshot on)
     - Staging
   * - Deploys from
     - ``origin/main``
     - ``origin/develop``
   * - Trust kit files
     - ``trust/.env.<CODE>.lza-prod``
     - ``trust/.env.<CODE>.lza-stag``

Separate kit file names mean self-contained kits are never overwritten.

Break-glass deploy from a laptop
================================

*Who: FLIP admin, only when CI is unavailable, or for the one-off account bootstrap before the first CI plan.*

.. code-block:: shell

   cd deploy/providers/AWS
   export AWS_PROFILE=lza-stag   # or: lza-prod
   export PROD=lza-stag          # or: lza

   make init
   make plan
   make apply
   make deploy-centralhub
   make deploy-ui

.. warning::

   On an account CI applies, the next pipeline run reverts a laptop ``apply``, and it shows as drift until then. Use
   it only to recover; "Break-glass" in the deployment README gives the conditions and per-estate commands.

.. note::

   - ``full-deploy``, ``make status`` and ``make destroy`` are built for the self-contained mode and are not yet
     tested here. Several ``full-deploy`` steps (the cloud trust EC2, SSH and Ansible setup) do not apply.
   - ``deploy-ui`` does not invalidate a CloudFront cache, because the edge distribution is in another account.
     Instead ``index.html`` is served uncached and the hashed assets as immutable.

***************
Further reading
***************

- `deploy/providers/AWS/README.md — Deploying onto an LZA estate
  <https://github.com/londonaicentre/FLIP/blob/main/deploy/providers/AWS/README.md#deploying-onto-an-lza-estate-prodlza>`_
  — the operator runbook.
- :ref:`security` — the "Cloud infrastructure" controls, including the estate-level ones the accelerator adds.
- The AI Centre's estate configuration (``londonaicentre/lza``) and its edge stack
  (``londonaicentre/aicentre-lza-iac``) are private repositories.
