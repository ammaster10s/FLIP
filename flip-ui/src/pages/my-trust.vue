<!--
    Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
-->

<route lang="yaml">
    name: My Trust
</route>

<!-- A Trust Admin's page (FLIP#1258): the projects staged at their trust — awaiting their decision, then decided —
     beside the trust itself as Connection Status shows it. -->
<template>
    <div class="flex flex-col w-full h-full">
        <div class="w-full px-8 pt-8 pb-8 overflow-y-auto">
            <div class="mb-4">
                <p class="text-xs font-mono uppercase tracking-widest text-gray-500 dark:text-gray-300">
                    Trust Admin · {{ trustAdminOf?.code ?? trustAdminOf?.name }}
                </p>
                <h1 class="text-3xl font-semibold font-heading mt-1 text-gray-900 dark:text-gray-100">
                    <span class="text-primary-600 underline decoration-4 decoration-primary-500/60 underline-offset-8 dark:text-white">My</span>
                    <span class="ml-2">trust</span>
                </h1>
            </div>

            <!-- Decisions first, the page's job; the trust's own connection card to their right (below them on narrow
                 screens). -->
            <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_410px]">
                <div class="space-y-6">
                    <AiCard>
                        <div class="px-6 py-5">
                            <h2 data-test="pending-heading" class="text-lg font-semibold text-gray-900 font-heading dark:text-gray-100">
                                Awaiting your decision ({{ pending.length }})
                            </h2>
                            <p v-if="!pending.length" data-test="nothing-pending" class="mt-2 text-sm text-gray-500 dark:text-gray-300">
                                Nothing awaiting your decision.
                            </p>
                            <ul data-test="pending-list" class="divide-y divide-gray-200 dark:divide-dark-border">
                                <TrustDecisionRow
                                    v-for="decision in pending"
                                    :key="decision.projectId"
                                    :decision="decision"
                                    :trust-name="trustName"
                                    @decide="askToDecide(decision, $event)"
                                />
                            </ul>
                        </div>
                    </AiCard>

                    <AiCard>
                        <div class="px-6 py-5">
                            <h2 class="text-lg font-semibold text-gray-900 font-heading dark:text-gray-100">
                                Decided
                            </h2>
                            <p v-if="!decided.length" class="mt-2 text-sm text-gray-500 dark:text-gray-300">
                                No decisions yet.
                            </p>
                            <ul data-test="decided-list" class="divide-y divide-gray-200 dark:divide-dark-border">
                                <TrustDecisionRow
                                    v-for="decision in decided"
                                    :key="decision.projectId"
                                    :decision="decision"
                                    :trust-name="trustName"
                                />
                            </ul>
                        </div>
                    </AiCard>
                </div>

                <AiCard data-test="trust-card-column">
                    <TrustDetailCard v-if="derivedTrust" :trust="derivedTrust" :hub-version="hubVersion" />
                    <div v-else class="p-6">
                        <AiLoader />
                    </div>
                </AiCard>
            </div>
        </div>

        <AiConfirmModal
            :dialog="!!choice"
            :submitting="submitting"
            :title="choice?.approve ? 'Approve project' : 'Decline project'"
            :confirmation-text="confirmationText"
            :continue-button-text="choice?.approve ? 'Approve' : 'Decline'"
            :continue-action="confirmDecision"
            @close-modal="choice = null"
        />
    </div>
</template>

<script setup lang="ts">
import useSWRV from "swrv";
import { computed, onBeforeMount, ref } from "vue";

import AiCard from "@/components/AiCard/AiCard.vue";
import AiLoader from "@/components/AiLoader/AiLoader.vue";
import AiConfirmModal from "@/components/AiModal/AiConfirmModal.vue";
import TrustDetailCard from "@/partials/connection/TrustDetailCard.vue";
import TrustDecisionRow from "@/partials/trusts/TrustDecisionRow.vue";
import { routeChange } from "@/router";
import { approveProject } from "@/services/project-service";
import { getHubHealth,
    getTrustDecisions,
    getTrustStatuses,
    IHubHealth,
    ITrustDecision,
    ITrustResponse } from "@/services/trust-service";
import { useAuthStore } from "@/store/auth";
import { extractErrorDetail } from "@/utils/api-errors";
import { deriveTrust } from "@/utils/connection-health";
import { Snackbar } from "@/utils/snackbar";

const authStore = useAuthStore();
const trustAdminOf = computed(() => authStore.trustAdminOf);

onBeforeMount(() => {
    if (!trustAdminOf.value) routeChange.viewProjects();
});

// Same key and cadence as Connection Status, so the two pages share one poll.
const { data: trusts } = useSWRV<ITrustResponse[]>("trust-connection-status", getTrustStatuses, {
    dedupingInterval: 5_000,
    shouldRetryOnError: false,
    refreshInterval: 15_000
});
const { data: hubHealth } = useSWRV<IHubHealth>("hub-health", getHubHealth, {
    dedupingInterval: 30_000,
    shouldRetryOnError: false,
    refreshInterval: 60_000
});
const hubVersion = computed<string | null>(() => hubHealth.value?.version ?? null);

const derivedTrust = computed(() => {
    const trust = (trusts.value ?? []).find(t => t.id === trustAdminOf.value?.id);

    return trust ? deriveTrust(trust) : null;
});
const trustName = computed(() => trustAdminOf.value?.name ?? "your trust");

// The header's pending badge uses this key too, so a decision here updates it.
const { data: decisions, mutate: refreshDecisions } = useSWRV<ITrustDecision[]>(
    () => (trustAdminOf.value ? `/trust/${trustAdminOf.value.id}/decisions` : null),
    () => getTrustDecisions(trustAdminOf.value!.id),
    {
        dedupingInterval: 5_000,
        shouldRetryOnError: false
    }
);
const pending = computed(() => (decisions.value ?? []).filter(d => d.status === "PENDING"));
const decided = computed(() => (decisions.value ?? []).filter(d => d.status !== "PENDING"));

const choice = ref<{ decision: ITrustDecision; approve: boolean } | null>(null);
const submitting = ref(false);

const askToDecide = (decision: ITrustDecision, what: "approve" | "decline") => {
    choice.value = {
        decision,
        approve: what === "approve"
    };
};

const confirmationText = computed(() => {
    if (!choice.value) return "";
    const { decision, approve } = choice.value;
    if (!approve) {
        return `Decline ${decision.projectName} for ${trustName.value}? The project will not use ${trustName.value}'s data.`;
    }
    const effect = decision.hasImaging
        ? `This starts the imaging pull at ${trustName.value}.`
        : `The project can then use ${trustName.value}'s data.`;

    return `Approve ${decision.projectName} for ${trustName.value}? ${effect}`;
});

const confirmDecision = async () => {
    if (!choice.value || !trustAdminOf.value) return;
    const { decision, approve } = choice.value;
    const trustId = trustAdminOf.value.id;
    submitting.value = true;
    try {
        await approveProject(`/step/project/${decision.projectId}/approve`, {
            approved: approve ? [trustId] : [],
            declined: approve ? [] : [trustId]
        });
        Snackbar.success({
            title: approve ? "Project approved" : "Project declined",
            text: `${decision.projectName} was ${approve ? "approved" : "declined"} for ${trustName.value}.`
        });
        await refreshDecisions();
    } catch (e) {
        Snackbar.error({
            title: "Decision not saved",
            text: extractErrorDetail(e, "The decision could not be saved, please try again.")
        });
    } finally {
        submitting.value = false;
        choice.value = null;
    }
};
</script>
