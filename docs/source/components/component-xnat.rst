.. _flip-xnat:

####
XNAT
####

`XNAT <https://www.xnat.org/>`_ is an open-source imaging informatics platform. It imports, archives, processes and
securely shares imaging and related study data. Each trust runs its own XNAT, which holds the imaging retrieved for
that trust's approved projects. The `XNAT wiki <https://wiki.xnat.org/documentation/how-to-use-xnat>`_ documents XNAT
itself.

This page is a quick reference to the XNAT UI tasks that come before training, and to how FLIP configures XNAT:
retrieval, anonymisation, DICOM-to-NIfTI conversion and the download calls training code uses.

**How a project reaches XNAT:**

1. When a FLIP project is approved, the hub queues an XNAT project-creation task for each trust that approved it. A
   trust that approves later gets its task then.
2. Each trust polls for its task and creates the XNAT project locally.
3. XNAT retrieves the cohort's imaging from the trust's :doc:`PACS <component-pacs>`.
4. The project's model developers get access to the XNAT project at each trust, to prepare and enrich the data before
   training.

.. contents:: On this page
   :local:
   :depth: 1

*******
XNAT UI
*******

.. _receiving-xnat-credentials:

Receiving XNAT account access
=============================

When a FLIP project is approved, its users get access to the matching XNAT project at each participating trust. XNAT
accounts are created where needed.

**If you are new to a trust's XNAT,** you receive an email at your FLIP address with a link to set your own password.
No password is ever sent by email. To use the link:

1. Replace the placeholder at the start of the link, ``<your trust's XNAT address>``, with the address you normally
   use for that trust's XNAT. The hub never knows a trust's internal XNAT address, so it cannot fill it in. The trust's
   XNAT administrator can tell you the address.
2. Keep the rest of the link (``/app/template/...``) exactly as shown.
3. Open it from a machine inside the trust's network. XNAT is only reachable there (see `Access`_).
4. Set your password. The link then stops working.

.. important::

   Unused links expire, **48 hours** after they were issued by default. Set your password promptly. See
   `Invite link lifetime`_.

**If you already have an account at that trust and have logged in to it,** being added to another project sends you a
notification instead. Log in with your existing password.

**If your account exists but you never logged in** (the first link was lost or expired), the next project approval
that includes you sends a fresh link. A missed invite is recovered by re-approval; no trust administrator needs to
reset the account.

.. _invite-link-lifetime:

Invite link lifetime
^^^^^^^^^^^^^^^^^^^^

FLIP does not set how long an unused link lasts, and does not read or override it. It is the trust XNAT's **Alias
Token Timeout** site setting, 48 hours by default:

  **Administer → Site Administration → Security → User Logins / Session Controls → Alias Token Timeout**

Setting a password through the link invalidates it, whatever the timeout.

.. warning::

   Raising the timeout extends the life of every invite link already sent. Treat it as a security setting, not a
   convenience.

Access
======

Each trust's XNAT is local to that trust. Model developers must be on the trust's local network to open the XNAT web
UI and do any data enrichment.

.. seealso::

   :ref:`data-enrichment`: what enrichment involves, where enrichment files must go so the FL client finds them, and
   how to upload a whole cohort's labels with the ``flip-xnat`` tool.

Login
=====

Open the XNAT URL. The landing page looks like this:

.. figure:: ../assets/xnat/XNAT_login.png
    :width: 600
    :align: center

    XNAT login page.

Enter the username and password from :ref:`receiving-xnat-credentials` and select **Login**. The home page lists
existing projects and has a project search:

.. figure:: ../assets/xnat/XNAT_home.png
    :width: 600
    :align: center

    XNAT homepage once logged in.

XNAT project structure and navigation
=====================================

.. list-table::
   :widths: 10 30
   :header-rows: 1

   * - Object
     - What it is
   * - Project
     - Created when the FLIP project is approved
   * - Subject
     - One individual. The anonymised ID is generated at random on import
   * - Experiment
     - CT session, labelled with the accession number
   * - Scan
     - A series of imaging data
   * - Resource
     - An individual imaging file, e.g. DICOM or NIfTI

See `Understanding the XNAT Data Model <https://wiki.xnat.org/documentation/how-to-use-xnat/understanding-the-xnat-data-model>`_
for more.

Project
^^^^^^^

An XNAT project created by FLIP is titled after its FLIP project: **`[FLIP Project Name]`:`[FLIP Project ID]`-FL-Project**.
For example, **Ischemic Stroke Vessel Occlusion:2fd45bc9-861b-4467-9b78-813372a10682-FL-Project**.

Open a project from the home page's project list or search.

.. figure:: ../assets/xnat/XNAT_project.png
    :width: 600
    :align: center

    An XNAT project.

The project page lists its subjects. More functions are in the **Actions** menu on the right.

Subject
^^^^^^^

Open a subject from a project's subject list.

.. figure:: ../assets/xnat/XNAT_subject.png
    :width: 600
    :align: center

    A specific subject.

The subject page lists its experiments (CT sessions). More functions are in the **Actions** menu on the right.

CT Session
^^^^^^^^^^

Open a CT session from a subject's list of experiments.

.. figure:: ../assets/xnat/XNAT_ct_session.png
    :width: 600
    :align: center

    A specific CT session.

A CT session comes from one PACS DICOM study. Its page lists the scans, with the imported DICOM images and the NIfTI
files converted from them.

Every FLIP XNAT includes the `OHIF viewer <https://wiki.xnat.org/xnat-ohif-viewer>`_. **View Images** in the
session's **Actions** menu opens the study in the browser. Use it to check an import, or to draw and save a
segmentation or ROI annotation as part of :ref:`data enrichment <data-enrichment>`.

Downloading and uploading imaging data
======================================

XNAT retrieves imaging from the trust's :doc:`PACS <component-pacs>` automatically when the project is created.
Model developers can download it, or upload new or amended imaging data. The XNAT wiki explains
`how to download and upload imaging data in the XNAT UI <https://wiki.xnat.org/documentation/how-to-use-xnat#HowToUseXNAT-UploadingImageDatatoXNAT>`_.

*****************************
Retrieval from the trust PACS
*****************************

XNAT's DICOM Query-Retrieve (DQR) plugin retrieves the imaging: XNAT queries the PACS for the studies in an approved
cohort, and the PACS sends them back for XNAT to archive.

.. seealso::

   :doc:`PACS <component-pacs>`: what the trust's PACS and network teams configure, the AE titles and ports, and how
   to verify the connection.

.. _dicom-anonymization:

*******************
DICOM anonymization
*******************

XNAT has a built-in anonymization engine that removes protected health information (PHI) from DICOM headers. FLIP
installs its own anonymization script site-wide. It runs on all data received through XNAT's DICOM receiver, before
the session is archived.

XNAT's stock script only writes the XNAT project, subject and session labels into three header fields. You can
fetch it with:

.. code-block:: bash

    curl -X GET "http://<xnat-host>/xapi/anonymize/default" -H "accept: text/plain"

FLIP anonymization script
=========================

FLIP's script is built from DICOM PS3.15 Table E.1-1 (2026d edition), the list of attributes the Basic Application
Level Confidentiality Profile acts on. It takes none of the profile's options. It:

- **Removes every attribute in the table**, wherever it occurs, including inside sequences. That covers names, IDs
  and addresses, the accession number, dates and times, the patient's age, sex, size and weight, free-text
  descriptions and comments, device and institution identifiers, overlays and curves, and whole sequences such as
  Original Attributes Sequence and Request Attributes Sequence. Where the table says to empty an attribute or give it
  a dummy value, the script removes it.
- **Removes every vendor private tag**, at any depth.
- **Replaces Patient Name and Patient ID** with the XNAT subject label (a random UUID for each import), and removes
  their nested copies.
- **Hashes every single-valued UID** at the top level, repeatably, so the objects of one study still reference each
  other. Copies inside sequences, and the three multi-valued UID attributes, are removed instead, because the engine
  cannot rewrite them.
- **Records the de-identification**: sets ``Patient Identity Removed`` to ``YES``, and a ``De-identification
  Method`` that states where the script falls short of PS3.15.

The images do not need dates, times or patient characteristics, because OMOP holds them. FL code joins an image to
its OMOP row through the accession number it asked the imaging API for, never through the DICOM headers.

**Archived file names.** By default XNAT names each file from its header as it arrived, before anonymization, starting
with the original Study Instance UID, and the FL client receives those names. FLIP changes the naming to the series
number, the instance number and a hash of the SOP Class and Instance UIDs. So
``<original Study Instance UID>-602172-1-1a8m7ai.dcm`` is archived as ``602172-1-1a8m7ai.dcm``. Files archived before
this setting keep their old names.

Limits of the profile
^^^^^^^^^^^^^^^^^^^^^

The script is **not a conformant PS3.15 profile**, and has only been run against synthetic studies. A trust that
connects a real PACS (see :doc:`component-pacs`) sends it real patient data, so these limits matter:

- **It removes where the profile empties.** The table empties some attributes a DICOM object must carry, such as
  Study Date and Patient's Sex. Without them a strict validator reports the object as non-conformant; XNAT, viewers
  and dcm2niix accept it.
- **Nested UIDs are removed, not replaced.** A reference held inside a sequence, such as a segmentation's link to the
  image it was drawn on, no longer resolves. The UID hash is also unkeyed, so anyone holding an original UID can
  recompute its hash, and the hash in each archived file's name.
- **The accession number is still the XNAT session label**, and the name of the folder FL code receives each study
  in. The headers no longer carry it. Replacing it with a per-project pseudonym is a known gap.
- **Burned-in annotation is untouched.** No header rule can reach identifiers rendered into the pixel data.
- **Faces are untouched.** A recognisable face can be rendered from the pixel data of a head CT or MRI. See
  :ref:`dicom-defacing`.

.. important::

   ``Patient Identity Removed = YES`` is only as strong as the rules above. A trust connecting a real PACS should
   review the profile against its own information-governance requirements, not read the tag as an assurance.

What the images lose:

- **Vendor fields that dcm2niix reads** for Siemens mosaic images (fMRI, diffusion), for diffusion directions, and
  for Philips' precise intensity scaling. These are private tags. CT, X-ray and structural MR convert without them.
- **The descriptive parts of NIfTI file names.** With no Protocol Name and no acquisition time, a CT series that
  converted as ``input_CT_Spleen_20140510112057_1.nii.gz`` now converts as ``input_000000_1.nii.gz``. The ``input_``
  prefix, the series number, the voxels and the geometry are unchanged, so **select scans by series number, not by
  name**.

.. _dicom-defacing:

De-facing (future work)
^^^^^^^^^^^^^^^^^^^^^^^

FLIP does not de-face images today. A possible addition is an XNAT Container Service command that removes the face
from head CT. An XNAT admin would enable it only for the projects that need it, then run it over a project from XNAT's
**Run Containers** launcher. Candidate tools:

- **TotalSegmentator's** ``face`` **task** (`TotalSegmentator <https://github.com/wasserth/TotalSegmentator>`__) is
  built for anonymisation. It is a licensed task: free for non-commercial use, with a commercial licence available
  from its author.
- **CTA-DEFACE** (`CTA-DEFACE <https://github.com/neuroAI-HD/CTA-DEFACE>`__) is a deep-learning de-facing model for
  CT. Its repository publishes no licence.
- **An openly licensed fallback.** TotalSegmentator's open model finds the brain and skull, then a
  `quickshear <https://github.com/nipy/quickshear>`__-style plane cut blanks everything in front of and below the
  brain. It removes more than the face, but carries no licence fees.

Anonymize API endpoints
=======================

FLIP uses these XNAT endpoints to install the script:

.. list-table::
    :widths: 10 30 30
    :header-rows: 1

    * - Method
      - Endpoint
      - Description
    * - GET
      - ``/xapi/anonymize/default``
      - Gets the default anonymization script
    * - PUT
      - ``/xapi/anonymize/site``
      - Sets the site-wide anonymization script
    * - PUT
      - ``/xapi/anonymize/site/enabled``
      - Enables or disables the site-wide anonymization script

.. admonition:: For maintainers
   :class: note

   The script is ``trust/xnat/xnat/config/anon_script.das``. XNAT setup installs it and sets the file-name template, and the
   receiver applies it while its ``anonymizationEnabled`` flag is ``true``. A copy of PS3.15 Table E.1-1 lives in
   ``trust/xnat/tests/ps315_table_e1_1.csv``, and a test fails when the script does not handle one of its rows. See
   :gh:`trust/xnat/README.md`.

*************************
DICOM to NIfTI conversion
*************************

XNAT can convert DICOM images to NIfTI automatically with ``dcm2niix``, run by its Container Service plugin. FLIP runs
the converter from its own version-pinned image, ``ghcr.io/londonaicentre/xnat-dcm2niix``, never a mutable
``latest`` tag. (The Docker Hub ``xnat/dcm2niix:latest`` image once resolved to an old build that silently dropped
slices from valid series.)

.. important::

   **XNAT stores the converter image when the command is registered.** An XNAT set up before a pin change keeps
   converting with the old image and still reports itself healthy.

   - Check what a deployment holds with ``GET /xapi/commands``, which lists each command's image.
   - Move it to the current image by re-running XNAT setup: the ``xnat-configure`` step on Compose, the
     ``xnat-init`` job on Kubernetes.

   Setup updates the existing command in place, so every project's trigger keeps working. The imaging API refuses to
   create a new project's trigger on a converter running another image, and its error names both images.

Commands vs event subscriptions
===============================

- A **command** (Container Service): FLIP registers ``dcm2niix`` as a command, enabled site-wide. Anyone can run it by
  hand in any project from the **Run Containers** action menu.
- An **event subscription** (Event Service): triggers a command when something happens in XNAT. FLIP creates one
  **per project**, listening for ``ScanEvent:CREATED`` (DICOM data archived) and running ``dcm2niix``.

Per-project configuration
=========================

The **Convert DICOMs to NIfTI** option on a FLIP project (``dicom_to_nifti``) controls its subscription:

- **On** (``dicom_to_nifti=True``): the subscription is active. ``dcm2niix`` runs whenever DICOM scans arrive, and the
  NIfTI files appear next to the DICOM data.
- **Off** (``dicom_to_nifti=False``): the subscription is created inactive. Nothing converts automatically, but
  ``dcm2niix`` can still be run by hand from the XNAT UI.

A subscription can be activated or deactivated later through the XNAT Event Service API. It fires on **new scans
only**. To convert scans archived while it was missing or broken, run from the repo root on the trust host:

.. code-block:: shell

   make -C trust reconvert-nifti KIT=<CODE>

Without ``LAUNCH=1`` it only reports what it would convert. On an on-prem host, prefix the command with ``sudo -E``.
See :ref:`ts-k8s-nifti-backlog` for what it selects and its options.

A project created with **Includes imaging data** turned off (``has_imaging=False``) never reaches XNAT. The hub skips
the imaging stage at approval, so no XNAT project, event subscription or PACS pull is created at any trust.

Event Service API endpoints
===========================

FLIP uses these XNAT endpoints to manage per-project subscriptions:

.. list-table::
    :widths: 10 30 30
    :header-rows: 1

    * - Method
      - Endpoint
      - Description
    * - POST
      - ``/xapi/projects/{project}/events/subscription``
      - Creates a project-scoped event subscription
    * - GET
      - ``/xapi/projects/{project}/events/subscriptions``
      - Lists all event subscriptions for a project
    * - DELETE
      - ``/xapi/projects/{project}/events/subscription/{id}``
      - Deletes an event subscription
    * - POST
      - ``/xapi/projects/{project}/events/subscription/{id}/activate``
      - Activates a deactivated subscription
    * - POST
      - ``/xapi/projects/{project}/events/subscription/{id}/deactivate``
      - Deactivates an active subscription
    * - GET
      - ``/xapi/events/allactions``
      - Lists the action key of every command wrapper (the imaging API reads dcm2niix's from it)
    * - PUT
      - ``/xapi/events/subscription/{id}``
      - Re-points a subscription at the current dcm2niix wrapper (the configure step, admin only)

.. admonition:: For maintainers
   :class: note

   A subscription names the ``dcm2niix-scan`` wrapper by id, as ``GET /xapi/events/allactions`` lists it. Setup keeps
   that id across redeploys by updating the command in place (``POST /xapi/commands/{id}``) rather than deleting and
   re-registering it, which would silently stop every existing project converting. On Docker Swarm, setup also
   registers ``ghcr.io`` as a credential-less Container Service image host, without which a launch fails even for a
   public image. Detail: :gh:`trust/xnat/README.md`.

*****************
FLIP XNAT methods
*****************

Training code can use these methods from the :gh:`flip-utils package <flip-utils/README.md>`:

``get_dataframe(self, project_id: str, query: str) -> DataFrame``
    Returns a DataFrame containing at least the accession IDs. Takes the project ID and the project query, both of
    which are already passed to the trainer.

``get_by_accession_number(project_id: str, accession_id: str, resource_type: ResourceType | list[ResourceType] = ResourceType.NIFTI) -> Path``
    Downloads the scans of the requested resource type (``NIFTI`` by default) into a directory the FL training script
    can read, and returns its path. Takes the project ID, an accession ID (from ``get_dataframe``) and an optional
    ``resource_type`` (one value or a list).

See :doc:`/components/component-fl-nets` for every ``flip.*`` call available to training code.
