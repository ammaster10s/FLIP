/*
 * Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { createTestingPinia } from "@pinia/testing";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

import type { ITrustDecision } from "@/services/trust-service";

import MyTrustPage from "../my-trust.vue";

const trustsRef = ref<unknown[] | undefined>(undefined);
const decisionsRef = ref<ITrustDecision[] | undefined>(undefined);
const mutateDecisions = vi.fn();

vi.mock("swrv", () => ({
    default: (keyFn: () => string | null) => {
        const key = typeof keyFn === "function" ? keyFn() : keyFn;
        if (typeof key === "string" && key.includes("/decisions")) {
            return {
                data: decisionsRef,
                mutate: mutateDecisions,
                error: ref(null)
            };
        }
        if (key === "hub-health") {
            return {
                data: ref({ version: "v0.9.0" }),
                mutate: vi.fn(),
                error: ref(null)
            };
        }

        return {
            data: trustsRef,
            mutate: vi.fn(),
            error: ref(null)
        };
    }
}));

const mockApproveProject = vi.fn();
vi.mock("@/services/project-service", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/services/project-service")>();

    return {
        ...actual,
        approveProject: (...args: unknown[]) => mockApproveProject(...args)
    };
});

const mockSnackbarSuccess = vi.fn();
const mockSnackbarError = vi.fn();
vi.mock("@/utils/snackbar", () => ({
    Snackbar: {
        success: (...args: unknown[]) => mockSnackbarSuccess(...args),
        error: (...args: unknown[]) => mockSnackbarError(...args),
        show: vi.fn(),
        warning: vi.fn()
    }
}));

const mockViewProjects = vi.fn();
vi.mock("@/router", () => ({
    routeChange: { viewProjects: (...args: unknown[]) => mockViewProjects(...args) },
    default: { push: vi.fn() }
}));

const TRUST_ADMIN_OF = {
    id: "dta",
    code: "DTA",
    name: "Decision Trust A"
};

const pending = (overrides: Partial<ITrustDecision> = {}): ITrustDecision => ({
    projectId: "p1",
    projectName: "Spleen segmentation v2",
    description: "Federated spleen segmentation on portal-venous CT.",
    ownerName: "Demo Researcher",
    projectStatus: "STAGED",
    hasImaging: true,
    stagedAt: "2026-09-25T10:00:00.000Z",
    query: "SELECT person_id FROM omop.person LIMIT 10",
    cohort: {
        recordCount: 142,
        suppressed: false,
        error: null
    },
    status: "PENDING",
    decidedByName: null,
    decidedAt: null,
    decidedAs: null,
    ...overrides
});

const stubs = {
    TrustDetailCard: {
        props: ["trust", "hubVersion"],
        template: "<div data-test='trust-card'>{{ trust.name }}</div>"
    },
    AiConfirmModal: {
        props: ["dialog", "continueAction", "confirmationText", "title", "continueButtonText"],
        emits: ["close-modal"],
        template: `<div v-if="dialog" data-test="confirm-modal">
            <p data-test="confirm-text">{{ confirmationText }}</p>
            <button data-test="confirm-modal-btn" @click="continueAction">{{ continueButtonText }}</button>
        </div>`
    }
};

function mountPage(trustAdminOf: typeof TRUST_ADMIN_OF | null = TRUST_ADMIN_OF) {
    return mount(MyTrustPage, {
        global: {
            plugins: [createTestingPinia({
                createSpy: vi.fn,
                stubActions: false,
                initialState: {
                    auth: {
                        user: {
                            permissions: ["CanCreateProjects"],
                            trustAdminOf
                        }
                    }
                }
            })],
            stubs
        }
    });
}

beforeEach(() => {
    vi.clearAllMocks();
    trustsRef.value = [
        {
            id: "dta",
            name: "Decision Trust A",
            code: "DTA",
            region: "London",
            last_heartbeat: new Date().toISOString(),
            project_count: 2,
            services: {},
            services_updated_at: null
        }
    ];
    decisionsRef.value = [
        pending(),
        pending({
            projectId: "p2",
            projectName: "EHR risk prediction",
            status: "APPROVED",
            projectStatus: "APPROVED",
            decidedByName: "Ada Admin",
            decidedAt: "2026-09-01T12:00:00.000Z",
            decidedAs: "SITE"
        })
    ];
});

describe("My Trust", () => {
    it("shows the Trust Admin's own trust card after the decisions (to their right on wide screens)", async () => {
        const wrapper = mountPage();
        await nextTick();

        expect(wrapper.find("[data-test='trust-card']").text()).toBe("Decision Trust A");
        // Source order puts the card after the decisions, so it follows them when the grid stacks.
        const html = wrapper.html();
        expect(html.indexOf("data-test=\"trust-card\"")).toBeGreaterThan(html.indexOf("data-test=\"decided-list\""));
        expect(wrapper.find("[data-test='trust-card-column']").exists()).toBe(true);
    });

    it("sends anyone who is not a Trust Admin back to Projects", async () => {
        mountPage(null);
        await flushPromises();

        expect(mockViewProjects).toHaveBeenCalled();
    });

    it("lists pending projects apart from decided ones", async () => {
        const wrapper = mountPage();
        await nextTick();

        expect(wrapper.find("[data-test='pending-heading']").text()).toContain("Awaiting your decision (1)");
        const pendingRows = wrapper.findAll("[data-test='pending-list'] [data-test='decision-row']");
        expect(pendingRows).toHaveLength(1);
        expect(pendingRows[0].text()).toContain("Spleen segmentation v2");
        const decidedRows = wrapper.findAll("[data-test='decided-list'] [data-test='decision-row']");
        expect(decidedRows[0].text()).toContain("Approved by Ada Admin");
    });

    it("expands a pending project to show what the decision needs", async () => {
        const wrapper = mountPage();
        await nextTick();

        await wrapper.find("[data-test='pending-list'] [data-test='decision-row-toggle']").trigger("click");

        expect(wrapper.find("[data-test='decision-cohort']").text()).toBe("142 records");
        expect(wrapper.find("[data-test='decision-query']").text()).toBe("SELECT person_id FROM omop.person LIMIT 10");
        expect(wrapper.find("[data-test='approve-btn']").exists()).toBe(true);
        expect(wrapper.find("[data-test='decline-btn']").exists()).toBe(true);
    });

    it.each([
        [null, "Not reported"],
        [{
            recordCount: 0,
            suppressed: true,
            error: null
        }, "Below the trust's disclosure threshold"],
        [{
            recordCount: null,
            suppressed: false,
            error: "boom"
        }, "Query failed"]
    ])("reports a cohort of %j as %s", async (cohort, text) => {
        decisionsRef.value = [pending({ cohort })];
        const wrapper = mountPage();
        await nextTick();

        await wrapper.find("[data-test='decision-row-toggle']").trigger("click");

        expect(wrapper.find("[data-test='decision-cohort']").text()).toBe(text);
    });

    it("approves only for this trust after confirming, then refreshes the list", async () => {
        mockApproveProject.mockResolvedValue({ projectStatus: "APPROVED" });
        const wrapper = mountPage();
        await nextTick();
        await wrapper.find("[data-test='decision-row-toggle']").trigger("click");

        await wrapper.find("[data-test='approve-btn']").trigger("click");
        expect(wrapper.find("[data-test='confirm-text']").text()).toContain(
            "Approve Spleen segmentation v2 for Decision Trust A?"
        );
        await wrapper.find("[data-test='confirm-modal-btn']").trigger("click");
        await flushPromises();

        expect(mockApproveProject).toHaveBeenCalledWith("/step/project/p1/approve", {
            approved: ["dta"],
            declined: []
        });
        expect(mutateDecisions).toHaveBeenCalled();
        expect(mockSnackbarSuccess).toHaveBeenCalled();
    });

    it("declines only for this trust after confirming", async () => {
        mockApproveProject.mockResolvedValue({ projectStatus: "STAGED" });
        const wrapper = mountPage();
        await nextTick();
        await wrapper.find("[data-test='decision-row-toggle']").trigger("click");

        await wrapper.find("[data-test='decline-btn']").trigger("click");
        await wrapper.find("[data-test='confirm-modal-btn']").trigger("click");
        await flushPromises();

        expect(mockApproveProject).toHaveBeenCalledWith("/step/project/p1/approve", {
            approved: [],
            declined: ["dta"]
        });
    });

    it("says so when nothing awaits a decision", async () => {
        decisionsRef.value = [];
        const wrapper = mountPage();
        await nextTick();

        expect(wrapper.find("[data-test='nothing-pending']").exists()).toBe(true);
    });
});
