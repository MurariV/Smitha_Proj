<template>
  <section class="card">
    <div class="card-header"><h1>{{ role === "Examiner" ? "Assigned Examinations" : "Examinations" }}</h1><button v-if="role === 'Admin'" class="btn btn-create" @click="editing = null">+ New Examination</button></div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <div class="toolbar"><input v-model="search" aria-label="Search examinations" class="form-control search-input" placeholder="Search examinations or courses..." /><select v-model="type" aria-label="Filter examination type" class="form-select filter-select"><option value="">All types</option><option>Viva</option><option>Practical</option><option>Project Demo</option><option>Assessment</option></select><select v-model="status" aria-label="Filter examination status" class="form-select filter-select"><option value="">All statuses</option><option>Draft</option><option>Slot Creation</option><option>Booking Open</option><option>Closed</option><option>Completed</option></select><button class="btn btn-outline-primary" @click="load">Refresh</button></div>
    <div class="table-responsive"><table class="table drive-table"><thead><tr><th>ID / Course</th><th>Examination</th><th>Type</th><th>Duration</th><th>Max Marks</th><th>Status</th><th>Action</th></tr></thead><tbody>
      <tr v-for="exam in filtered" :key="exam.id"><td>#{{ exam.id }}<small class="d-block text-secondary">{{ exam.course_code }}</small></td><td><strong>{{ exam.name }}</strong><small class="d-block text-secondary">{{ exam.course }}</small></td><td>{{ exam.exam_type }}</td><td>{{ exam.duration }} min</td><td>{{ exam.maximum_marks }}</td><td><span class="badge" :class="statusClass(exam.archived ? 'Archived' : exam.status)">{{ exam.archived ? "Archived" : exam.status }}</span><small v-if="exam.published_at" class="d-block text-success mt-1">Results published</small></td><td class="actions-cell"><RouterLink :to="`${base}/examinations/${exam.id}`" class="btn btn-sm action view">View Details</RouterLink><button v-if="role === 'Admin' && !exam.archived" class="btn btn-sm btn-outline-primary" @click="editing = exam">Edit</button></td></tr>
      <tr v-if="!filtered.length"><td colspan="7" class="empty-text">{{ loading ? "Loading examinations..." : "No examinations match your search." }}</td></tr>
    </tbody></table></div>
    <ExamForm v-if="editing !== undefined" :exam="editing" @close="editing = undefined" @saved="editing = undefined; message = 'Examination saved.'; load(); $emit('changed')" />
  </section>
</template>
<script>
import { api, session, statusClass } from "../services/api";
import ExamForm from "./ExamForm.vue";
export default {
  emits: ["changed"],
  components: { ExamForm }, data: () => ({ items: [], search: "", type: "", status: "", editing: undefined, loading: false, error: "", message: "" }),
  computed: {
    role() { return session.user.role; }, base() { return `/${this.role.toLowerCase()}`; },
    filtered() { return this.items.filter(e => `${e.name} ${e.course} ${e.course_code}`.toLowerCase().includes(this.search.toLowerCase()) && (!this.type || e.exam_type === this.type) && (!this.status || e.status === this.status)); },
  },
  mounted() { this.load(); },
  methods: { statusClass, async load() { this.loading = true; this.error = ""; try { this.items = (await api("/examinations")).items; } catch (e) { this.error = e.message; } finally { this.loading = false; } } },
};
</script>
