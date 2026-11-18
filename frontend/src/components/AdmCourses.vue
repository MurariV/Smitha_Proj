<template>
  <section class="card">
    <div class="card-header"><h1>Courses</h1><button class="btn btn-create" @click="edit()">+ New Course</button></div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <div class="toolbar"><input v-model="search" aria-label="Search courses" class="form-control search-input" placeholder="Search by course name or code..." /><button class="btn btn-outline-primary" @click="load">Refresh</button></div>
    <div class="table-responsive"><table class="table drive-table"><thead><tr><th>ID</th><th>Course Code</th><th>Course Name</th><th>Description</th><th>Status</th><th>Action</th></tr></thead><tbody>
      <tr v-for="course in filtered" :key="course.id"><td>{{ course.id }}</td><td><strong>{{ course.code }}</strong></td><td>{{ course.name }}</td><td class="description-cell">{{ course.description }}</td><td><span class="badge" :class="statusClass(course.status)">{{ course.status }}</span></td><td class="actions-cell"><button class="btn btn-sm action view" @click="edit(course)">Edit</button><button v-if="course.status === 'Active'" class="btn btn-sm action delete" @click="archive(course)">Archive</button></td></tr>
      <tr v-if="!filtered.length"><td colspan="6" class="empty-text">{{ loading ? "Loading..." : "No courses match your search." }}</td></tr>
    </tbody></table></div>
    <Modal v-if="form" :title="form.id ? 'Edit Course' : 'Create Course'" :busy="busy" @close="form = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <form @submit.prevent="save"><label class="form-label" for="course-code">Course code</label><input id="course-code" v-model="form.code" class="form-control mb-3" required maxlength="30" />
        <label class="form-label" for="course-name">Course name</label><input id="course-name" v-model="form.name" class="form-control mb-3" required maxlength="150" />
        <label class="form-label" for="course-description">Description</label><textarea id="course-description" v-model="form.description" class="form-control mb-3" rows="3" maxlength="3000"></textarea>
        <label v-if="form.status === 'Archived'" class="form-check"><input class="form-check-input" type="checkbox" v-model="reactivate" /><span class="form-check-label">Reactivate this course</span></label>
        <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="form = null">Cancel</button><button class="btn btn-primary" :disabled="busy">Save Course</button></div>
      </form>
    </Modal>
  </section>
</template>
<script>
import { api, statusClass } from "../services/api";
import Modal from "./Modal.vue";
export default {
  components: { Modal },
  data: () => ({ items: [], search: "", form: null, reactivate: false, busy: false, loading: false, error: "", modalError: "", message: "" }),
  computed: { filtered() { const q = this.search.toLowerCase(); return this.items.filter((c) => `${c.code} ${c.name}`.toLowerCase().includes(q)); } },
  mounted() { this.load(); },
  methods: {
    statusClass,
    async load() { this.error = ""; this.loading = true; try { this.items = (await api("/admin/courses")).items; } catch (e) { this.error = e.message; } finally { this.loading = false; } },
    edit(item) { this.form = item ? { ...item } : { code: "", name: "", description: "", status: "Active" }; this.reactivate = false; this.modalError = ""; },
    async save() {
      this.busy = true; this.modalError = "";
      try { await api(`/admin/courses${this.form.id ? `/${this.form.id}` : ""}`, { method: this.form.id ? "PUT" : "POST", body: { ...this.form, status: this.reactivate ? "Active" : this.form.status } }); this.form = null; this.message = "Course saved."; await this.load(); }
      catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
    async archive(course) {
      if (!window.confirm(`Archive ${course.name}? Historical examination records will be preserved.`)) return;
      try { await api(`/admin/courses/${course.id}`, { method: "DELETE" }); this.message = "Course archived."; await this.load(); } catch (e) { this.error = e.message; }
    },
  },
};
</script>
