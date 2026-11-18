<template>
  <div class="popup-overlay">
  <div class="popup-box" role="dialog" aria-modal="true" :aria-label="title">
    <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
      <h2 id="popup-title" class="mb-0">{{ title }}</h2>
      <button type="button" class="btn-close mt-2" :disabled="busy" aria-label="Close dialog" @click="$emit('close')"></button>
    </div>
    <slot />
  </div>
  </div>
</template>
<script>
export default {
  props: { title: String, busy: Boolean },
  emits: ["close"],
};
</script>
