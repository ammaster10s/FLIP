##############
FLIP workflow
##############

This page follows one project from cohort query to trained model. Each section names who acts and links to the
step-by-step guide in :doc:`user-guides`.

Each diagram is a swimlane: one column per person or service, time running downwards.

.. contents:: On this page
   :local:
   :depth: 1

************
Cohort query
************

*Who: researcher*

The researcher creates a project, adds its members and writes an SQL cohort query against the :term:`OMOP` data model.
FLIP runs the query at every registered Trust. Each Trust returns aggregate statistics only, and hides any count
below its own minimum group size. The researcher can refine and re-run the query until the cohort is large enough.

See :ref:`create-cohort-query`.

.. mermaid::
   :caption: Cohort query. The trust polls the hub; nothing connects into the trust.

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


****************
Project approval
****************

*Who: researcher, then each Trust's* :term:`Trust Admin` *or a FLIP admin*

The researcher chooses the Trusts whose data they need and **stages** the project. Staging locks the project details
and cohort query.

Each staged Trust then approves or declines the project in its own time. The decision is agreed offline with the
Trust's information governance team and recorded in FLIP by the Trust's own Trust Admin, or by a FLIP admin if the
Trust has none. FLIP records who decided and when.

- The project is **approved** as soon as one Trust approves it. A Trust that approves later joins the project then.
- A Trust that **declines** takes no further part: its data is never imported or trained on.
- If every Trust declines, the project stays staged. A FLIP admin can unstage it so the researcher can amend it.

When a Trust approves, it fixes the project's cohort: from then on, training sees only the patients and studies the
approved query returned. The Trust's XNAT then retrieves those studies from the Trust's :term:`PACS`, and each project
member is given access to the project in that XNAT.

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


.. note::

   **Tabular-only projects.** A project created with 'Includes imaging data' turned off skips every imaging step:
   approval creates no XNAT project and pulls nothing from PACS, there is nothing to enrich, and training reads the
   OMOP cohort data alone. You still switch on the 'Dataset enriched' confirmation before training; for these
   projects it confirms that the data is ready. Like 'Convert DICOMs to NIfTI', this option is fixed when the project
   is created.

****************
Image enrichment
****************

*Who: project members (optional)*

Once a Trust's XNAT has retrieved the images, project members can log in to that XNAT and segment, label or
otherwise annotate them before training. Only members of the FLIP project can see its images in XNAT. The project
page shows each Trust's import progress.

Enrichment is needed only when the model uses data that is **not in OMOP**, such as segmentation masks and other
image-derived annotations. Labels that are already in OMOP, such as a lab result or a coded report finding, reach
the model as a column of the cohort query and need no enrichment.

See :ref:`data-enrichment` for both routes, and for uploading labels by hand in the XNAT web UI or by script across a
whole cohort.

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
       M->>Hub: Confirm the dataset is enriched


************
File uploads
************

*Who: researcher*

The researcher creates a model in the project and uploads its training and validation code, with any other files
the code needs. See :doc:`working-with-flip-apps` for how to write the code and which files a job requires.

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


*********
Job start
*********

*Who: researcher*

When the images are ready and the code is uploaded, the researcher confirms that the dataset is enriched and starts
training. FLIP queues the job until a training net is free, then sends the uploaded code to every approving Trust.

At each Trust, the code receives the approved cohort as a dataframe and downloads the images it needs from that
Trust's XNAT. Training code can also write derived files, such as processed images, back to the XNAT project for
later runs.

See the *Training* section of :doc:`user-guides/user-common`.

.. mermaid::
   :caption: Job start. FL clients hold an outbound connection to the FL server.

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
       R->>Hub: Start training at chosen trusts
       Hub->>Hub: Queue until an FL net is free
       Hub->>S: Submit job with the uploaded code
       S->>C: Send the app to each trust
       C->>DA: Cohort dataframe (approved cohort only)
       C->>IA: Images for each accession number
       IA->>X: Download study
       IA-->>C: Image files


**********
Job finish
**********

Training runs in rounds. After each round, every Trust sends its filtered model update to the Central Hub, which
combines the updates and sends the combined model back out for the next round.

When the last round finishes, the final model and any metrics the code recorded are available to project members in
the FLIP UI. See :ref:`view-results`.

.. mermaid::
   :caption: Training rounds and job finish.

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

