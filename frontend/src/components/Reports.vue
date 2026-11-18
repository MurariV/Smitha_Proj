<template>
  <section class="card">
    <div class="card-header">
      <h1>Monthly Examination Report</h1>
      <div class="d-flex gap-2"><button class="btn btn-outline-primary" @click="load">Refresh</button><button class="btn btn-create" :disabled="busy" @click="queueReport">Email Monthly Report</button></div>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <p>{{ report.month }}</p>
    <div class="table-responsive">
      <table class="table drive-table">
        <thead><tr><th>Statistic</th><th>Total</th></tr></thead>
        <tbody><tr v-for="metric in metrics" :key="metric.key"><td>{{ metric.label }}</td><td>{{ report[metric.key] ?? 0 }}</td></tr></tbody>
      </table>
    </div>
    <h2 class="h5 mt-4">Most Active Examiners</h2>
    <div class="table-responsive">
      <table class="table drive-table">
        <thead><tr><th>Examiner</th><th>Evaluations</th></tr></thead>
        <tbody><tr v-for="person in report.examiner_workload" :key="person.name"><td>{{ person.name }}</td><td>{{ person.evaluations }}</td></tr><tr v-if="!report.examiner_workload?.length"><td colspan="2" class="empty-text">No evaluations in this reporting month.</td></tr></tbody>
      </table>
    </div>
  </section>
</template>
<script>
import { api } from "../services/api";
export default {
  data: () => ({
    report: {}, error: "", message: "", busy: false,
    metrics: [
      { key: "examinations_conducted", label: "Examinations conducted" },
      { key: "students_evaluated", label: "Students evaluated" },
      { key: "completed_bookings", label: "Completed bookings" },
      { key: "pending_evaluations", label: "Pending evaluations" },
    ],
  }),
  mounted() { this.load(); },
  methods: {
    async load() {
      this.error = "";
      try { this.report = await api("/admin/reports"); }
      catch (error) { this.error = error.message; }
    },
    async queueReport() {
      this.busy = true; this.error = "";
      try { this.message = (await api("/admin/reports/monthly", { method: "POST" })).message; }
      catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
