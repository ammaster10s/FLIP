.. _deploy-flip-node-on-prem:

###############################
Deploy a FLIP node on-prem
###############################

An on-prem FLIP node runs the trust-side stack (trust-api, imaging-api, data-access-api, the FL client and optional
XNAT/Orthanc) on an Ubuntu host owned by the Trust. Use this model when the Trust has direct, governed access to its
own OMOP database and PACS.

The node polls the Central Hub for work over HTTPS. **All traffic to the hub is outbound**: no inbound ports are
opened to the internet. The one exception is retrieval from the Trust's own PACS, which needs a rule inside the
Trust's network (see :doc:`../components/component-pacs`).

.. seealso::

   :doc:`deploy-flip-node-in-tre` to deploy inside a TRE, and :doc:`deploy-central-hub` for the hub side.

.. contents:: On this page
   :local:
   :depth: 2

************
Architecture
************

.. code-block:: text

            Internet
                │
                ▼
        ┌──────────────────┐
        │   AWS Central     │
        │   Hub             │
        └─▲──────────────▲─┘
          │              │
   polls  │              │  polls
  (HTTPS) │              │ (HTTPS)
          │              │
   ┌──────┴───┐    ┌─────┴───────┐
   │ Trust A   │    │ Trust B      │
   │ (AWS EC2) │    │ (on-prem)    │
   └──────────┘    └─────────────┘

An on-prem trust runs the same Docker Compose stack as a cloud trust. Its services talk over the internal Docker
network and publish no container ports on the host, so the stack can share a machine with the dev stack without
port conflicts.

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Service
     - Container port
     - Traffic
   * - trust-api
     - 8000
     - HTTP; polls the hub outbound
   * - imaging-api
     - 8000
     - HTTP, internal only
   * - data-access-api
     - 8000
     - HTTP, internal only
   * - fl-client
     - —
     - TCP, outbound to the FL server via the hub's network load balancer (NLB)

*************
Prerequisites
*************

Deployment workstation
======================

The machine the FLIP admin runs the hub-side commands from, typically a laptop. It needs:

- Python 3.12 or 3.13 and `UV <https://docs.astral.sh/uv/guides/install-python/>`_. Ansible is installed for you by
  ``uv sync`` in ``deploy/providers/AWS/``.
- The Central Hub already deployed from it (``make init`` and ``make apply`` in ``deploy/providers/AWS/``), so its
  Terraform outputs are available.
- SSH access to the trust host, if you provision it remotely with the hybrid flow.

Trust host
==========

An Ubuntu 22.04+ machine (physical or VM) with:

- A user with ``sudo`` rights (default ``ubuntu``), reachable over SSH from the workstation or used locally.
- Internet access, to pull Docker images and packages.
- A writable directory for FLIP (default ``/opt/flip``).
- **For GPU training or evaluation:** an NVIDIA GPU on driver **580 or newer** (check *Driver Version* in
  ``nvidia-smi``) and the
  `NVIDIA Container Toolkit <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>`_.
  The FL images bring their own CUDA 13 runtime, so the host needs no CUDA toolkit. The provisioning playbook installs
  neither the driver nor the toolkit. A CPU-only host (``NUM_AVAILABLE_GPUS=0`` in the kit) needs neither.

Trust data
==========

The node reads two systems. Both must already exist, and agree with each other, before you deploy:

- An **OMOP database** (PostgreSQL) holding the Trust's clinical data in the ``omop`` schema: OMOP CDM 5.4 plus the
  MI-CDM imaging tables (``image_occurrence``, ``image_feature``). FLIP reads it through a read-only role and writes
  nothing back.
- A **PACS** that answers a study-level query by accession number. Agree the checklist in
  :doc:`../components/component-pacs` with your PACS manager.

**The accession number links the two.** Every imaging row in ``image_occurrence`` must carry, in its ``accession_id``
column, the accession number the PACS answers to for that study (DICOM tag ``(0008,0050)``). This column is FLIP's
own addition to MI-CDM, so a standard OMOP ETL does not create it: your data team adds and fills it during the OMOP
load. :ref:`omop-accession-id` has the DDL and what to fill it from.

Rows may be per study or per series; FLIP imports each study once. Each value must be exactly one study's accession
number:

- never empty;
- never containing ``*``, ``?`` or ``\``. A PACS treats these as wildcards, so FLIP refuses to send them. The row is
  dropped with a warning in the imaging-api log, and **that study is never pulled**.

.. important::

   The deployment checks neither system. A gap only shows up when the first project's imaging pull runs, so confirm
   both with the data and PACS teams first.

Central Hub
===========

The hub must be deployed in AWS (:doc:`deploy-central-hub-aws`) before the trust can resolve the hub URL, fetch its
FL participant kit and be let through the FL load balancer. On a Landing Zone Accelerator estate the FL entry point
is the networking account's edge instead (:doc:`deploy-central-hub-aws-lza`). Shared prerequisites are in
:doc:`deploy-central-hub`.

.. note::

   On the trust host, every command that touches Docker runs with ``sudo``. The provisioning playbook deliberately
   does not add the login user to the ``docker`` group, because membership is equivalent to root access.

************************************
Recommended end-to-end (hybrid) flow
************************************

*Who: someone with hub AWS access who can also reach the trust host.* One wrapper deploys the Central Hub, registers
the trusts and provisions the on-prem trust.

#. **Deploy the hub and provision the trust.**

   .. code-block:: shell

      cd deploy/providers/AWS
      make full-deploy-hybrid PROD=<stag|true> [LOCAL_TRUST_IP=<public-ip>]

   ``PROD=stag`` targets staging, ``PROD=true`` production. Leave out ``LOCAL_TRUST_IP`` to use the workstation's
   own public IP, detected automatically.

#. **Start the trust stack on the host.** Use the trust code you scaffolded:

   .. code-block:: shell

      cd ../../..
      sudo -E env PROD=<stag|true> make -C trust up-trust KIT=<CODE>

#. **Check the trust is polling.**

   .. code-block:: shell

      sudo docker logs -f trust<N>-trust-api-1

   You should see successful task polls against the Central Hub. ``<N>`` is the FL kit slot number the hub assigned
   (``FL_KIT_SLOT_NUMBER`` in the kit file); every trust container is named ``trust<N>-<service>-1``.

******************************************
Onboarding an on-prem trust (step by step)
******************************************

Use this when the Central Hub is already running. Onboarding is split between two people, and neither needs access
to the other's machines:

- The **FLIP admin** holds production AWS credentials. They create, register and package the trust's **kit**.
- The **trust operator** has no AWS access. They install the kit on the trust host and start the stack.

``<CODE>`` is the trust's short code. Its kit file is ``trust/.env.<CODE>.production``.

Step 1 — Create the kit
=======================

*Who: FLIP admin*

.. code-block:: shell

   make new-trust TRUST_CODE=<CODE> TRUST_NAME="<trust name>" PROD=true

This writes ``trust/.env.<CODE>.production`` with host defaults, placeholder local passwords and
``<run-make-register-trust>`` placeholders for the values the hub manages.

Step 2 — Register the trust on the hub
======================================

*Who: FLIP admin*

.. code-block:: shell

   make -C deploy/providers/AWS register-trusts KIT=<CODE> PROD=true

This registers the trust with the production hub and writes the trust's **credentials** into its kit file (API key,
internal service key, FL slot and expected trust id). Most of the **hub-shared settings**, including the encryption
key and the hub URL, are still placeholders afterwards; step 3 fills them.

.. important::

   The hub keeps only hashes of these credentials and cannot show them again. Keep the kit file safe; to rotate the
   credentials, register the trust again.

Step 3 — Fill in the hub-shared settings
========================================

*Who: FLIP admin.* Run from the repo root, with your local ``.env.production`` present.

.. code-block:: shell

   make sync-trust-kit KIT=<CODE> PROD=true

This copies the hub-shared settings from your local env file into the kit and leaves the credentials from step 2
untouched.

.. important::

   Do not skip this step. Without it the kit's encryption key and hub URL stay as placeholders, and the trust can
   neither reach the hub nor decrypt a task.

.. seealso::

   ``deploy/providers/AWS/README.md``, "Registering trusts against the ECS hub", for the same flow from the hub side.

Step 4 — Package and send the kit
=================================

*Who: FLIP admin*

.. code-block:: shell

   make -C deploy/providers/AWS package-onprem-trust-kit KIT=<CODE> PROD=true

This bundles the completed kit file with this trust's share of the FL participant kit (fetched from S3) into a
tarball under ``deploy/providers/AWS/build/trust-kits/``. It does not modify the kit file.

.. warning::

   The tarball holds a plaintext API key, the AES encryption key and an FL TLS private key. Send it to the operator
   over an encrypted channel only.

Step 5 — Install the kit
========================

*Who: trust operator, on the trust host*

#. **Check out the release the hub runs.** The admin tells you the version (the hub's ``/api/health`` also reports
   it). Never use a branch tip: the compose files and Makefiles that run the images come from this checkout.

   .. code-block:: shell

      git fetch --tags origin && git checkout v<X.Y.Z>

#. **Extract the tarball and copy the kit file into the checkout.**

   .. code-block:: shell

      tar -xzf flip-trust-kit-<slot>-<date>.tar.gz
      cp .env.<CODE>.production trust/

   Keep the extracted ``net-1/`` folder exactly as it is: the stack mounts that layout into the FL client.

#. **Edit** ``trust/.env.<CODE>.production`` **for your host.** Change only the settings below. Leave the
   *Hub-shared* and *Kit credentials* blocks alone; they are managed by the admin.

   .. list-table::
      :header-rows: 1
      :widths: 30 55 15

      * - Setting
        - What to set
        - Required?
      * - ``FL_KIT_DIR``
        - Path to the extracted FL kit (the folder that contains ``net-1/``).
        - Yes
      * - ``XNAT_PORT`` and ``XNAT_WEB_PORT``
        - XNAT's DICOM receiver port and its web UI port. Both are published on the host, so they **must differ**
          (shipped defaults: 8104 and 8105).
        - Yes
      * - Other host ports, e.g. ``OMOP_DB_PORT``
        - Change any that clash with something already on the host.
        - If needed
      * - Storage and bind-mount directories
        - Point them at your host's disk layout.
        - If needed
      * - Trust-local passwords
        - Replace every default password in the *Trust-local credentials* section with a real secret.
        - Yes
      * - ``NUM_AVAILABLE_GPUS``
        - Number of GPUs for FL jobs; ``0`` on a CPU-only host.
        - If needed
      * - ``FL_SITE_PRIVACY_POLICY`` and its parameters
        - Your site's own privacy filter on FL updates (NVFLARE only). See
          :ref:`onprem-site-privacy-policy`.
        - Optional

.. note::

   **Upgrading a trust deployed before the XNAT port split.** ``XNAT_PORT`` used to cover both the DICOM receiver and
   the web UI; the web UI now has its own ``XNAT_WEB_PORT``. A kit that sets only ``XNAT_PORT`` gives both the same
   number, so the next ``up-onprem-trust`` is **refused** with a message naming both values and the file to edit.
   That refusal is expected: add ``XNAT_WEB_PORT`` (for example 8105) to the kit before your next deployment.

Step 6 — Run the readiness checklist and start the stack
========================================================

*Who: trust operator*

.. code-block:: shell

   sudo -E make onboard-onprem-trust KIT=<CODE> PROD=true   # readiness checklist
   sudo -E make up-onprem-trust KIT=<CODE> PROD=true        # starts only if every check passes

The checklist prints a ✅ or ❌ for each of: your public IP, Docker swarm state, the hub-shared settings and
credentials being filled in, ``FL_KIT_DIR`` being set and present, and the FL kit contents. Fix every ❌ row;
``up-onprem-trust`` runs the same checks and will not start until they pass.

Send the **Your public IP** value to the FLIP admin for step 7.

.. tip::

   The checklist changes nothing, so you can run it at any time, even before the kit is fully in place, just to read
   off your public IP.

Step 7 — Open the FL load balancer to the trust
===============================================

*Who: FLIP admin*

#. Add the trust's public IP to ``LOCAL_TRUST_PUBLIC_IPS`` in your hub env file (``.env.production``). It is an HCL
   list, for example ``LOCAL_TRUST_PUBLIC_IPS=["1.2.3.4"]``.

#. Apply it:

   .. code-block:: shell

      make -C deploy/providers/AWS allow-local-trust-nlb LOCAL_TRUST_IP=<public-ip> PROD=true

   This checks the IP is in the list, then runs a normal Terraform plan and apply. The rule is ordinary config, so
   later full applies show no drift.

Step 8 — Check the trust is polling
===================================

*Who: trust operator*

.. code-block:: shell

   sudo docker logs -f trust<N>-trust-api-1

You should see successful task polls against the Central Hub. ``<N>`` is ``FL_KIT_SLOT_NUMBER`` from the kit file.

.. _onprem-site-privacy-policy:

Optional — set a site privacy policy (NVFLARE)
==============================================

*Who: trust operator*

As the data holder, you can apply your own privacy filter to everything the FL client sends to the FL server,
whatever the researcher's app configures.

#. In ``trust/.env.<CODE>.production``, uncomment ``FL_SITE_PRIVACY_POLICY`` and, optionally, its parameters.
#. Run ``make onboard-onprem-trust`` to validate them. An invalid combination stops the FL client at startup, by
   design.
#. After ``up-onprem-trust``, the FL client log shows ``[site-privacy] site privacy policy ACTIVE: ...``.

To change or remove the policy later, edit the kit file and restart the FL clients:

.. code-block:: shell

   make -C trust up-fl-clients-kit KIT=<CODE> PROD=true

.. seealso::

   :doc:`../components/component-fl-nets`, "Site-enforced privacy policy", for the parameters and how they are
   enforced.

Later — rotate hub-shared settings
==================================

When the admin changes a hub-shared value (the encryption key, image tags or FL backend), the credentials do not need
to be re-issued.

#. *FLIP admin:* refresh the kit, then send it to the operator over the same encrypted channel.

   .. code-block:: shell

      make sync-trust-kit KIT=<CODE> PROD=true

#. *Trust operator:* replace only the *Hub-shared* block in your kit file, then apply it:

   .. code-block:: shell

      sudo -E make upgrade-onprem-trust KIT=<slot> YES=1

.. warning::

   Do not use ``up-onprem-trust`` on a running trust. It is the first-install command and resets XNAT.

Later — upgrade to a new release
================================

*Who: trust operator*

.. code-block:: shell

   sudo -E make upgrade-onprem-trust KIT=<slot>

By default this moves the site to the release the hub runs.

.. seealso::

   :doc:`/sys-admin/admin-upgrading-sites` for the full runbook, including when the admin must re-issue kits first.

.. _onprem-core-vocabulary:

*****************************
Load the OMOP core vocabulary
*****************************

*Who: trust operator, once, after the first* ``up-onprem-trust``

The node's OMOP database starts without the OMOP core vocabulary: SNOMED CT, LOINC and the other licensed
vocabularies that cohort queries resolve concepts through. Each site downloads its own copy under its own licences;
the AI Centre cannot hand on its copy, because the licences do not clearly allow that redistribution.

.. warning::

   Without the vocabulary the node starts and passes every health check, but any cohort query that resolves
   core-vocabulary concepts returns nothing.

#. **Download the vocabularies.** You need at least those in the
   `core vocabulary roster <https://github.com/londonaicentre/FLIP/blob/develop/trust/omop-db/README.md#the-core-vocabulary-bundle>`_.

   - From `OHDSI Athena <https://athena.ohdsi.org/>`_, with your own account, accepting each vocabulary's licence.
   - The UK editions (SNOMED CT UK, dm+d, Read v2) from `NHS TRUD <https://isd.hscic.gov.uk/trud/>`_, under the NHS
     national licences.

#. **Unzip the export into one directory.** The loader reads these nine files from its top level: ``CONCEPT.csv``,
   ``CONCEPT_ANCESTOR.csv``, ``CONCEPT_CLASS.csv``, ``CONCEPT_RELATIONSHIP.csv``, ``CONCEPT_SYNONYM.csv``,
   ``DOMAIN.csv``, ``DRUG_STRENGTH.csv``, ``RELATIONSHIP.csv`` and ``VOCABULARY.csv``.

#. **Load it** from the checkout on the trust host. You need ``psql`` (``sudo apt-get install postgresql-client``).
   Take the four ``OMOP_*`` values from your kit file:

   .. code-block:: shell

      cd trust/omop-db
      OMOP_DB_HOST=127.0.0.1 OMOP_DB_PORT=<OMOP_DB_PORT> OMOP_POSTGRES_DB=<OMOP_POSTGRES_DB> \
        OMOP_POSTGRES_USER=<OMOP_POSTGRES_USER> OMOP_POSTGRES_PASSWORD='<OMOP_POSTGRES_PASSWORD>' \
        ./files/load_core_vocab.sh <export dir> files/OMOPCDM_postgresql_5.4_constraints.sql

   The full roster takes about 25 minutes. Re-running is safe: tables that already hold the vocabulary are skipped.

#. **Check it.** With the same variables, ``./files/load_core_vocab.sh --check`` loads nothing and exits 0 once every
   table is loaded.

#. **If a cohort query ran before the load,** restart data-access-api so it drops its cached (empty) results:

   .. code-block:: shell

      sudo docker restart trust<N>-data-access-api-1

.. note::

   On a Helm-deployed node, leave ``omopDb.vocabLoad.s3Bucket`` empty and run the same loader over a
   ``kubectl port-forward`` to the ``omop-db`` service. The chart README (``trust/deploy/helm/README.md``, "Local
   clusters (kind)") shows how; use your own export in place of its ``make fetch-vocab-core`` step.

***********************
Trust authentication
***********************

The hub identifies a trust by its **API key**, not by IP address or hostname: any host with the right credentials in
its kit file can act as that trust. The kit file must contain:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Purpose
   * - ``TRUST_API_KEY``
     - The trust's secret, sent on every call to the hub.
   * - ``CENTRAL_HUB_API_URL``
     - The public hub URL the trust polls, e.g. ``https://app.flip.aicentre.co.uk``.
   * - ``AES_KEY_BASE64``
     - The encryption key shared with the hub for task payloads (AES-256-GCM). It must match the hub's key exactly;
       a mismatch fails every task with ``failed authentication``. Trusts must be upgraded together with their hub
       across the move to AES-256-GCM, because payloads in the older format are not accepted.
   * - ``TRUST_INTERNAL_SERVICE_KEY``
     - A per-trust secret the trust's own services use to authenticate one another. It never leaves the trust.
   * - ``EXPECTED_TRUST_ID`` (optional)
     - A self-check. If set, and the hub resolves this host's API key to a different trust, trust-api stops instead
       of acting as the wrong trust.

Before the trust can connect, it must be **registered on the hub**, either by step 2 above or through the Add-Trust
admin flow. Registration also writes the API key and internal service key into the kit file. No hub redeploy is
needed: the hub reads its trust list live on every request.

***********************
Network requirements
***********************

**No inbound port forwarding from the internet is needed.** Trusts poll the hub for tasks, and FL clients connect
out to the FL server. (Retrieval from a trust PACS needs one rule inside the Trust's own network; see
:doc:`../components/component-pacs`.)

The trust host must reach two **separate** hub endpoints. They have different hostnames behind different load
balancers, so allow both:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Endpoint
     - Example host
     - Port
   * - Central Hub API (HTTPS)
     - ``app.flip.aicentre.co.uk``
     - 443
   * - FL server (gRPC or HTTP)
     - ``fl.app.flip.aicentre.co.uk``
     - The kit's ``FL_EDGE_PORT``, else ``FL_SERVER_PORT``: 8002 on production, 8003 on LZA staging

**If the trust's public IP changes** (common on residential broadband), the FLIP admin adds the new IP to
``LOCAL_TRUST_PUBLIC_IPS`` in the hub env file (``.env.stag`` or ``.env.production``) and re-applies, as in step 7:

.. code-block:: shell

   make -C deploy/providers/AWS allow-local-trust-nlb LOCAL_TRUST_IP=<new-ip> PROD=<stag|true>

***************
Troubleshooting
***************

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Check
   * - Trust not polling the hub
     - Is the stack running (``sudo docker ps`` on the trust host)? Look for polling errors in the trust-api logs.
   * - ``Connection timed out`` (FL)
     - Has the trust's public IP changed? Update the NLB allow-list (see `Network requirements`_).
   * - Firewall blocking outbound traffic
     - Make sure the host and router firewalls allow outbound HTTPS (443) and the FL port (``FL_EDGE_PORT``, default
       8002; 8003 on LZA staging).
   * - Ansible ``Permission denied``
     - Is the SSH key correct? Does the user have ``sudo``? In local-host mode, is ``ANSIBLE_BECOME_PASS`` set?
