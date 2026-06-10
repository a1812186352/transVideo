<template>
  <div class="migration-bar">
    <!-- ── Left: Steps ── -->
    <div class="migration-bar__steps">
      <div
        v-for="(step, i) in steps"
        :key="i"
        class="migration-bar__step"
        :class="{
          'migration-bar__step--done': step.done,
          'migration-bar__step--active': !step.done && (i === 0 || steps[i - 1]?.done),
        }"
      >
        <span class="migration-bar__step-icon">
          <template v-if="step.done">&#10003;</template>
          <template v-else-if="!step.done && (i === 0 || steps[i - 1]?.done)">
            <span class="migration-bar__spinner"></span>
          </template>
          <template v-else>&mdash;</template>
        </span>
        <span class="migration-bar__step-label">{{ step.label }}</span>
        <span v-if="i < steps.length - 1" class="migration-bar__step-connector"></span>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
defineProps<{
  steps: Array<{ label: string; done: boolean }>;
}>();
</script>

<style scoped>
.migration-bar {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 16px;
  gap: 24px;
}

/* ── Steps ── */
.migration-bar__steps {
  display: flex;
  align-items: center;
  gap: 0;
  flex: 1;
}

.migration-bar__step {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
  position: relative;
}

.migration-bar__step--done {
  color: var(--slot-closing);
}

.migration-bar__step--active {
  color: var(--accent);
}

.migration-bar__step-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-surface);
}

.migration-bar__step--done .migration-bar__step-icon {
  border-color: var(--slot-closing);
  background: var(--slot-closing);
  color: #fff;
}

.migration-bar__step--active .migration-bar__step-icon {
  border-color: var(--accent);
}

/* Spinner animation */
.migration-bar__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.migration-bar__step-label {
  white-space: nowrap;
}

.migration-bar__step-connector {
  width: 20px;
  height: 1px;
  background: var(--border);
  margin: 0 4px;
  flex-shrink: 0;
}

.migration-bar__step--done + .migration-bar__step .migration-bar__step-connector,
.migration-bar__step--done .migration-bar__step-connector {
  background: var(--slot-closing);
}
</style>