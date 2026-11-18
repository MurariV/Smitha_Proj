<template>
  <section>
    <div class="page-heading">
      <h1>{{ role }} Dashboard</h1>
      <RouterLink v-if="role === 'Admin'" to="/admin/reports" class="btn btn-create">Monthly Report</RouterLink>
      <RouterLink v-if="role === 'Examiner'" to="/examiner/slots" class="btn btn-create">Manage Slots</RouterLink>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div class="row g-3 mb-4">
      <div v-for="(value, key) in counts" :key="key" class="col-6 col-md-4 col-xl">
        <div class="dcard">
          <h2>{{ label(key) }}</h2><strong>{{ value }}</strong>
          <RouterLink v-if="role === 'Admin'" :to="`/admin/${key}`" class="btn btn-sm action view">Manage {{ label(key) }}</RouterLink>
        </div>
      </div>
    </div>
    <Examinations class="mb-4" @changed="load" />
    <Bookings @changed="load" />
  </section>
</template>
<script>
import { api, session } from "../services/api";
import Examinations from "./Examinations.vue";
import Bookings from "./Bookings.vue";
export default {
  components: { Examinations, Bookings },
  data: () => ({ counts: {}, error: "" }),
  computed: { role() { return session.user.role; } },
  mounted() { this.load(); },
  methods: {
    label(value) { return value.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()); },
    async load() {
      this.error = "";
      try { this.counts = (await api(`/${this.role.toLowerCase()}/dashboard`)).counts; }
      catch (error) { this.error = error.message; }
    },
  },
};
</script>
