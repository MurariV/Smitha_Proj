<template>
  <section class="card">
    <div class="card-header"><h1>{{ role === "Examiner" ? "My Examination Slots" : "Examination Slots" }}</h1><button v-if="role === 'Examiner'" class="btn btn-create" @click="edit()">+ Create Slot</button></div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <div class="toolbar"><input v-model="search" aria-label="Search slots" class="form-control search-input" placeholder="Search examination, examiner or location..." /><select v-model="examFilter" aria-label="Filter slots by examination" class="form-select filter-select"><option value="">All examinations</option><option v-for="exam in exams" :key="exam.id" :value="exam.id">{{ exam.name }}</option></select><button class="btn btn-outline-primary" @click="load">Refresh</button></div>
    <div class="table-responsive"><table class="table drive-table"><thead><tr><th>ID / Examination</th><th>Examiner</th><th>Start / End</th><th>Capacity</th><th>Location</th><th>Status</th><th>Action</th></tr></thead><tbody><tr v-for="slot in filtered" :key="slot.id"><td>#{{ slot.id }}<strong class="d-block">{{ slot.examination }}</strong></td><td>{{ slot.examiner }}</td><td>{{ formatDate(slot.start) }}<small class="d-block text-secondary">{{ formatDate(slot.end) }}</small></td><td>{{ slot.booked }} / {{ slot.capacity }} booked<small class="d-block text-secondary">{{ slot.available_seats }} available</small></td><td>{{ slot.location || "Online / TBC" }}<a v-if="slot.meeting_link" class="d-block" :href="slot.meeting_link" target="_blank" rel="noopener noreferrer">Meeting Link</a></td><td><span class="badge" :class="statusClass(slot.status)">{{ slot.status }}</span></td><td class="actions-cell">
      <RouterLink v-if="role === 'Student'" :to="`/student/examinations/${slot.exam_id}`" class="btn btn-sm action view">View / Book</RouterLink>
      <template v-else><button class="btn btn-sm action view" :disabled="['Completed','Cancelled'].includes(slot.status)" @click="edit(slot)">{{ role === "Admin" ? "Reschedule / Reassign" : "Edit" }}</button><button v-if="role === 'Examiner'" class="btn btn-sm action delete" :disabled="['Completed','Cancelled'].includes(slot.status)" @click="remove(slot)">Remove</button><button v-if="role === 'Examiner'" class="btn btn-sm action done" :disabled="busy || ['Completed','Cancelled'].includes(slot.status)" @click="complete(slot)">Complete</button></template>
    </td></tr><tr v-if="!filtered.length"><td colspan="7" class="empty-text">{{ loading ? "Loading slots..." : "No examination slots found." }}</td></tr></tbody></table></div>
    <Modal v-if="form" :title="form.id ? (role === 'Admin' ? 'Reschedule / Reassign Slot' : 'Edit Examination Slot') : 'Create Examination Slot'" :busy="busy" @close="form = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <form @submit.prevent="save">
        <label for="slot-exam" class="form-label">Examination</label><select id="slot-exam" v-model.number="form.exam_id" class="form-select mb-3" :disabled="!!form.id" required @change="updateEnd"><option disabled value="">Select examination</option><option v-for="exam in exams" :key="exam.id" :value="exam.id">{{ exam.name }} ({{ exam.duration }} min)</option></select>
        <div class="row g-3"><div class="col-md-6"><label for="slot-start" class="form-label">Start time</label><input id="slot-start" v-model="form.start" type="datetime-local" class="form-control" required @change="updateEnd" /></div><div class="col-md-6"><label for="slot-end" class="form-label">End time</label><input id="slot-end" v-model="form.end" type="datetime-local" class="form-control" required /></div></div>
        <label for="slot-capacity" class="form-label mt-3">Maximum student capacity</label><input id="slot-capacity" v-model.number="form.capacity" type="number" min="1" max="500" class="form-control mb-3" required />
        <label for="slot-location" class="form-label">Location</label><input id="slot-location" v-model="form.location" class="form-control mb-3" maxlength="200" />
        <label for="slot-link" class="form-label">Meeting link (optional)</label><input id="slot-link" v-model="form.meeting_link" type="url" class="form-control mb-3" maxlength="500" placeholder="https://..." />
        <template v-if="role === 'Admin'"><label for="slot-examiner" class="form-label">Assigned examiner</label><select id="slot-examiner" v-model.number="form.examiner_id" class="form-select mb-3" required><option v-for="user in selectedExam?.examiners || []" :key="user.id" :value="user.id">{{ user.name }}</option></select><label for="slot-reason" class="form-label">Reason for exceptional change</label><textarea id="slot-reason" v-model="form.reason" class="form-control" required maxlength="1000" rows="3"></textarea></template>
        <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="form = null">Cancel</button><button class="btn btn-primary" :disabled="busy">Save Slot</button></div>
      </form>
    </Modal>
  </section>
</template>
<script>
import { api, session, formatDate, statusClass, toISO, toLocalInput } from "../services/api";
import Modal from "./Modal.vue";
export default {
  components: { Modal },
  data: () => ({ items: [], exams: [], search: "", examFilter: "", form: null, busy: false, loading: false, error: "", modalError: "", message: "" }),
  computed: {
    role() { return session.user.role; },
    selectedExam() { return this.exams.find(e => e.id === this.form?.exam_id); },
    filtered() { return this.items.filter(s => (!this.examFilter || s.exam_id === this.examFilter) && `${s.examination} ${s.examiner} ${s.location}`.toLowerCase().includes(this.search.toLowerCase())); },
  },
  mounted() { this.load(); },
  methods: {
    formatDate, statusClass,
    async load() {
      this.error = ""; this.loading = true;
      try {
        this.exams = (await api("/examinations")).items;
        this.items = (await api(`/${this.role.toLowerCase()}/slots`)).items;
      } catch (e) { this.error = e.message; } finally { this.loading = false; }
    },
    edit(slot) {
      this.modalError = "";
      this.form = slot ? { ...slot, start: toLocalInput(slot.start), end: toLocalInput(slot.end), reason: "" } : { exam_id: "", start: "", end: "", capacity: 1, location: "", meeting_link: "" };
    },
    updateEnd() {
      if (this.form.start && this.selectedExam) this.form.end = toLocalInput(new Date(Date.parse(this.form.start) + this.selectedExam.duration * 60000).toISOString());
    },
    async save() {
      this.busy = true; this.modalError = "";
      try {
        await api(`/${this.role.toLowerCase()}/slots${this.form.id ? `/${this.form.id}` : ""}`, { method: this.form.id ? "PUT" : "POST", body: { ...this.form, start: toISO(this.form.start), end: toISO(this.form.end) } });
        this.form = null; this.message = "Slot saved."; await this.load();
      } catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
    async remove(slot) {
      if (!window.confirm("Remove this slot? Slots with booking history cannot be removed.")) return;
      try { await api(`/examiner/slots/${slot.id}`, { method: "DELETE" }); this.message = "Slot removed."; await this.load(); } catch (e) { this.error = e.message; }
    },
    async complete(slot) {
      if (!window.confirm("Mark this slot complete? All booked students must already be evaluated.")) return;
      this.busy = true;
      try { this.message = (await api(`/examiner/slots/${slot.id}/complete`, { method: "POST" })).message; await this.load(); } catch (e) { this.error = e.message; } finally { this.busy = false; }
    },
  },
};
</script>
