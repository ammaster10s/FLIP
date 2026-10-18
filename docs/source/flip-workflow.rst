##############
FLIP workflow
##############

This page follows one project from the first cohort query to a trained model. It explains what happens at each stage,
who acts, and what stays inside each trust. The step-by-step instructions for the web interface are in
:doc:`user-guides`.

.. list-table::
   :header-rows: 1
   :widths: 22 30 48

   * - Stage
     - Who acts
     - Outcome
   * - `Cohort query`_
     - Researcher
     - The researcher knows how many matching patients each trust holds.
   * - `Project approval`_
     - Researcher, then each trust
     - Approving trusts fix the cohort and pull its images into their own XNAT.
   * - `Image enrichment`_
     - Project members (optional)
     - Images carry the labels or segmentations the model needs.
   * - `File uploads`_
     - Researcher
     - The model's code and configuration are on the hub, checked.
   * - `Job start`_
     - Researcher
     - The code is running at every approving trust, on that trust's data.
   * - `Training and results`_
     - Automatic
     - A trained model and its metrics are ready to download.

**How to read the diagrams.** Each diagram is a swimlane: one column per person or service, with time running
downwards. The numbers on the arrows match the numbered steps in the text. Services on the left run in the Central
Hub; services on the right run inside each trust.

.. important::

   **Nothing connects into a trust.** A trust's services fetch their work from the Central Hub by polling it, and its
   FL client opens its own connection to the FL server. Patient-level data never leaves the trust; only aggregate
   statistics, filtered model updates, training metrics and status information reach the hub.

************
Cohort query
************

*Who: researcher*

Before asking any trust to take part, the researcher checks that enough suitable patients exist. They describe the
cohort as an SQL query against the :term:`OMOP` data model, and FLIP runs it at every registered trust.

.. mermaid::
   :caption: Cohort query.

   sequenceDiagram
       autonumber
       actor R as Researcher
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
       end
       box rgb(234, 237, 242) Each trust
           participant TA as trust-api
           participant DA as data-access-api
           participant O as OMOP
       end
       R->>Hub: Create project, write cohort query
       R->>Hub: Run on all trusts
       Hub->>Hub: Queue a cohort query task per trust
       TA->>Hub: Poll for tasks
       Hub-->>TA: Cohort query task (encrypted)
       TA->>DA: Run the query
       DA->>O: Validated, read-only SQL
       O-->>DA: Matching rows
       DA-->>TA: Aggregate statistics, small counts hidden
       TA->>Hub: Post results
       Hub-->>R: Cohort size per trust

**1–2.** The researcher creates a project, adds its members, writes the cohort query and runs it on all trusts.

**3–5.** The hub queues one task per trust. Each trust picks up its task the next time it polls the hub, a few seconds
later.

**6–8.** At the trust, ``data-access-api`` checks the query (a single read-only ``SELECT`` on the OMOP schema) and runs
it against the trust's own OMOP database.

**9–11.** The trust sends back **aggregate statistics only**, never patient rows. Any count below the trust's own minimum
group size is hidden. The researcher sees the cohort size per trust and can refine and re-run the query until the
cohort is large enough.

.. seealso::

   :ref:`create-cohort-query`.

****************
Project approval
****************

*Who: the researcher stages the project; each trust's* :term:`Trust Admin` *(or a FLIP admin, if the trust has
none) approves or declines it*

Every trust decides for itself whether its patients' data may be used. Approval is also the moment the cohort is fixed
and, for imaging projects, the images are fetched.

.. mermaid::
   :caption: Project approval and image retrieval at one trust.

   sequenceDiagram
       autonumber
       actor R as Researcher
       actor A as Trust Admin or FLIP admin
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
       end
       box rgb(234, 237, 242) Each trust
           participant TA as trust-api
           participant DA as data-access-api
           participant IA as imaging-api
           participant X as XNAT
           participant P as PACS
       end
       R->>Hub: Stage project at chosen trusts
       A->>Hub: Approve (agreed with the trust's IG team)
       Hub->>Hub: Queue freeze-cohort, then create-imaging task
       TA->>Hub: Poll for tasks
       Hub-->>TA: Both tasks, run in order
       TA->>DA: Freeze cohort membership
       DA-->>TA: Membership stored at the trust
       TA->>Hub: Report frozen cohort
       TA->>IA: Create imaging project
       IA->>X: Create XNAT project, add project members
       IA->>DA: Cohort accession numbers
       IA->>X: Retrieve these studies
       X->>P: DICOM query / retrieve
       P-->>X: Studies
       TA->>Hub: Import progress (on later polls)
       Hub-->>R: Imaging status on the project page

**1.** The researcher chooses the trusts whose data they need and **stages** the project. Staging locks the project details
and the cohort query.

**2.** Each staged trust decides in its own time. The decision is agreed offline with the trust's information governance
team, then recorded in FLIP. FLIP records who decided and when.

**3–5.** On approval, the hub queues two tasks for that trust, which it runs in order on its next poll.

**6–8.** **The cohort is frozen.** The trust runs the approved query once and stores the list of patients and studies it
returned, at the trust. From now on, training sees only those patients and studies: a patient removed from OMOP drops
out, but no new patient can join.

**9–14.** **The images are fetched.** ``imaging-api`` creates a project in the trust's :term:`XNAT` and gives each project
member access to it. It then asks XNAT to retrieve the cohort's studies from the trust's :term:`PACS`, using their
accession numbers. The images stay in that trust's XNAT.

**15–16.** The trust reports import progress on its later polls, and the researcher follows it on the project page.

How the decisions combine:

- The project is **approved** as soon as one trust approves it. A trust that approves later joins at that point.
- A trust that **declines** takes no further part: its data is never imported or trained on.
- If every trust declines, the project stays staged. A FLIP admin can unstage it so the researcher can amend it.

.. note::

   **Tabular-only projects.** A project created with **Includes imaging data** turned off skips steps 9–16: approval
   creates no XNAT project and pulls nothing from PACS, there is nothing to enrich, and training reads the OMOP cohort
   data alone. Like **Convert DICOMs to NIfTI**, this option is fixed when the project is created.

.. seealso::

   :ref:`stage-project`, :ref:`project-approval` and :ref:`imaging-status`.

****************
Image enrichment
****************

*Who: project members (optional)*

Trust PACS hold images, not the labels or segmentations a model may learn from. Enrichment is where project members add
them, inside each trust's XNAT.

**Do you need it?** Only when the model uses data that is **not in OMOP**, such as segmentation masks or other
annotations drawn on the images. Labels that are already in OMOP, such as a lab result or a coded report finding,
reach the model as a column of the cohort query and need no enrichment.

.. mermaid::
   :caption: Image enrichment, inside each trust's XNAT.

   sequenceDiagram
       autonumber
       actor M as Project member
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
       end
       box rgb(234, 237, 242) Each trust
           participant X as XNAT
       end
       Hub-->>M: Images imported (project page)
       M->>X: Sign in with the XNAT credentials FLIP sent
       M->>X: Add segmentations, labels or annotations

**1.** When the project page shows a trust's images as imported, enrichment can start there.

**2.** Project members sign in to that trust's XNAT with the credentials FLIP emailed them. Only members of the FLIP
project can see its images.

**3.** They add the annotations, either by hand in the XNAT web interface or by script across the whole cohort.

.. seealso::

   :ref:`data-enrichment` covers both routes.

************
File uploads
************

*Who: researcher*

The model is the code FLIP will run at each trust. The researcher writes it as an FL app and uploads it to the hub.

.. mermaid::
   :caption: File uploads.

   sequenceDiagram
       autonumber
       actor R as Researcher
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
       end
       R->>Hub: Create a model in the project
       R->>Hub: Upload training code and configuration
       Hub->>Hub: Check required files and scan uploads
       Hub-->>R: Files listed on the model page

**1.** The researcher creates a model in the approved project. A project can hold several models.

**2.** They upload the training code, its configuration and any other files the code needs.

**3.** The hub checks that every file the job type requires is present and scans each upload.

**4.** The files are listed on the model page, ready for training.

.. seealso::

   :doc:`working-with-flip-apps` for how to write the code and which files each job type requires, and
   :ref:`upload-model-files`.

*********
Job start
*********

*Who: researcher*

Training starts once the images are in place and the code is uploaded. FLIP sends the same code to every approving
trust, where it runs next to the data.

.. mermaid::
   :caption: Job start.

   sequenceDiagram
       autonumber
       actor R as Researcher
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
           participant S as FL server
       end
       box rgb(234, 237, 242) Each approving trust
           participant C as FL client
           participant DA as data-access-api
           participant IA as imaging-api
           participant X as XNAT
       end
       R->>Hub: Confirm dataset enriched, start training
       Hub->>Hub: Queue until an FL net is free
       Hub->>S: Submit job with the uploaded code
       S->>C: Send the app to each trust
       C->>DA: Cohort dataframe (approved cohort only)
       C->>IA: Images for each accession number
       IA->>X: Download study
       IA-->>C: Image files

**1.** On the model page, the researcher switches on **Dataset enriched** (required even when no enrichment was needed),
picks the participating trusts and starts training.

**2.** FLIP queues the job until one of its training networks (*FL nets*) is free.

**3–4.** The hub's FL server receives the job and sends the code to the FL client at each participating trust.

**5.** At each trust, the code receives the frozen cohort as a table of rows from OMOP.

**6–8.** It downloads the images it needs from that trust's XNAT. The code can also write derived files, such as
processed images, back to the XNAT project for later runs.

.. seealso::

   :ref:`initiate-training`.

********************
Training and results
********************

*Who: automatic; the researcher collects the results*

Federated training runs in **rounds**. Each trust trains on its own data, and only the model changes travel to the
hub, where they are combined into one model.

.. mermaid::
   :caption: Training rounds and results.

   sequenceDiagram
       autonumber
       actor R as Researcher
       box rgb(248, 234, 242) Central Hub
           participant Hub as Hub API and UI
           participant S as FL server
       end
       box rgb(234, 237, 242) Each approving trust
           participant C as FL client
       end
       loop Every round
           S->>C: Current global model
           C->>C: Train on local data
           C->>S: Filtered model update and metrics
           S->>S: Combine the updates
           S->>Hub: Metrics
       end
       S->>Hub: Final model and results
       Hub-->>R: Metrics charts, Download Results

**1–2.** The FL server sends the current model to each trust, which trains it on local data.

**3.** Each trust sends back its **model update**, filtered before it leaves the trust, together with the metrics the
code recorded.

**4–5.** The FL server combines the updates into the next global model and passes the metrics to the hub, where they
appear as charts on the model page while training runs.

**6–7.** After the last round, the final model and results are stored on the hub. Project members download them with

**Download Results**.

.. seealso::

   :ref:`training-metrics` and :ref:`view-results`.
