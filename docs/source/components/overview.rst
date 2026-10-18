.. _components-overview:

########
Overview
########

************
Architecture
************

FLIP has two parts:

1. A **cloud-hosted Central Hub**, where researchers define machine learning projects, find suitable datasets at
   participating Trusts, and train and test models across those Trusts. The results are aggregated into one
   consensus model.
2. A **Secure Enclave** (a *FLIP node*) at each Trust, which only runs training requests the Trust itself has fetched
   from the hub. FLIP's microservices run inside the enclave next to the Trust's imaging archive, its :term:`OMOP`
   database and the GPUs its FL client trains on. Training and evaluation happen inside the enclave, on the Trust's
   own data, and **only model updates leave**.

.. figure:: ../assets/support/flip_architecture-flip_architecture.png
   :align: center

   FLIP architecture.

Central Hub
===========

The Central Hub is the cloud environment where researchers define a cohort and start federated training. Role-based
access control limits each user to their own data.

Researchers define the cohort for training and testing from the Trusts' data, view statistics about it and refine
their query until they settle on a dataset. The model is then sent to the Secure Enclave at each selected Trust,
trained and tested there, and the results are aggregated centrally.

The hub is the only internet-facing part of FLIP. :doc:`component-central-hub` describes its services, and
:ref:`deploy-central-hub` how they are laid out on AWS in either supported deployment mode.

Secure Enclave
==============

The Secure Enclave runs FLIP's trust side at each Trust, so models are trained and tested on the Trust's own GPU
hardware. **No personally identifying data leaves the enclave.**

Three FastAPI services, ``trust-api``, ``imaging-api`` and ``data-access-api``, run as containers next to XNAT, the
OMOP database and one FL client per net. They run under Docker Compose or from the Kubernetes Helm chart.

Nothing on the hub connects in to a Trust. The ``trust-api`` polls the hub for work over outbound HTTPS, and the FL
client opens an outbound connection to the FL server, so a Trust needs no inbound firewall rule for FLIP itself. See
:doc:`component-trust-apis`.

**********
Components
**********

Each component below has its own page; this section is the map.

Central Hub
===========

The hub runs:

- the web UI (``flip-ui``);
- the central API (``flip-api``) and its PostgreSQL database;
- the hub half of every FL net;
- an OIDC identity provider for sign-in: AWS Cognito on AWS, Keycloak in local development;
- S3 storage for model files and results.

See :doc:`component-central-hub` for the services and :ref:`deploy-central-hub` for their layout on AWS.

FL nets
=======

Federated learning runs on either :term:`NVIDIA FLARE` or :term:`Flower Framework`, deployed as a set of *nets*.
Each net is an FL API and FL server on the hub plus one FL client at each Trust. The hub's scheduler gives each queued
training job to whichever net is free.

:doc:`component-fl-nets` also covers job types, required files, training configuration and the privacy filters
applied to model updates.

Trust APIs
==========

The three trust-side services: ``trust-api`` fetches tasks from the hub and reports results; ``imaging-api``
drives XNAT (project creation, retrieval from PACS, conversion, downloads for training); ``data-access-api``
runs validated cohort queries against OMOP. See :doc:`component-trust-apis`.

OMOP Database
=============

The `OMOP <https://www.ohdsi.org/data-standardization/>`_ Common Data Model gives every Trust's electronic
health data the same shape, so one cohort query runs unchanged at each site. FLIP adds the MI-CDM imaging tables,
which link records to accession numbers. Each Trust holds it in a PostgreSQL database inside its enclave. See
:doc:`component-omop-database`.

XNAT
====

:term:`XNAT` stores the imaging retrieved for a project (DICOM series and the NIfTI files converted from them) and
controls access to it. It anonymises and converts the images as they arrive. One XNAT runs at each Trust. See
:doc:`component-xnat`.

PACS
====

The Trust's own Picture Archiving and Communication System. XNAT retrieves an approved cohort's studies from it by
DICOM query/retrieve. FLIP never holds a copy of the PACS. In development, a mocked Orthanc server stands in for it.
See :doc:`component-pacs`.

Logging Stack
=============

Structured JSON logs from the trust services, collected by Grafana Alloy into Loki and viewed in Grafana, all
inside the Trust. See :doc:`component-logging-stack`.

Deployment targets
==================

The Central Hub is provisioned on AWS with Terraform/OpenTofu, either self-contained in one account or on a Landing
Zone Accelerator estate (:ref:`deploy-central-hub`).

A Trust node runs in one of three ways:

- as a Docker Compose stack on a host inside the Trust (:doc:`/deploy-flip/deploy-flip-node-on-prem`);
- inside a Trusted Research Environment (:doc:`/deploy-flip/deploy-flip-node-in-tre`);
- on Kubernetes, from the Helm chart (:gh:`Helm chart README <trust/deploy/helm/README.md>`).

The AWS-hosted mock Trusts used for staging run the same Compose stack on an EC2 instance.
