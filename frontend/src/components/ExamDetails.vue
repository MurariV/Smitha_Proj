<template>
  <div>
    <RouterLink :to="`${base}/examinations`" class="back-link">&larr; Back to Examinations</RouterLink>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }} <button class="btn btn-sm btn-outline-danger" @click="load">Refresh</button></div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <template v-if="exam">
      <section class="card mb-4">
        <div class="card-header"><div><p class="eyebrow">{{ exam.course_code }} &middot; {{ exam.course }}</p><h1>{{ exam.name }}</h1></div><span class="badge fs-6" :class="statusClass(exam.archived ? 'Archived' : exam.status)">{{ exam.archived ? "Archived" : exam.status }}</span></div>
        <div class="row g-3 details-grid"><div class="col-md-3"><span>Examination Type</span><strong>{{ exam.exam_type }}</strong></div><div class="col-md-3"><span>Duration</span><strong>{{ exam.duration }} minutes</strong></div><div class="col-md-3"><span>Maximum Marks</span><strong>{{ exam.maximum_marks }}</strong></div><div class="col-md-3"><span>Results</span><strong>{{ exam.published_at ? "Published" : "Not published" }}</strong></div></div>
        <div class="row g-3 mt-2"><div class="col-md-6"><div class="timeline-card"><h2 class="h6">Examiner Slot Creation</h2><p>{{ formatDate(exam.slot_creation_start) }} &rarr;<br />{{ formatDate(exam.slot_creation_end) }}</p></div></div><div class="col-md-6"><div class="timeline-card"><h2 class="h6">Student Slot Booking</h2><p>{{ formatDate(exam.booking_start) }} &rarr;<br />{{ formatDate(exam.booking_end) }}</p></div></div></div>
        <h2 class="h5 mt-4">Assigned Examiners</h2><p>{{ exam.examiners.map(e => e.name).join(", ") }}</p>
        <div class="job-desc-container"><h2 class="h5">Examination Instructions</h2><p class="preserve-lines mb-0">{{ exam.instructions || "Please bring your student ID and arrive on time." }}</p></div>
        <div v-if="role === 'Admin' && !exam.archived" class="admin-controls mt-4">
          <label for="exam-phase" class="form-label mb-0">Examination phase</label><select id="exam-phase" v-model="nextStatus" class="form-select filter-select" :disabled="busy || loading || !!exam.published_at"><option>Draft</option><option>Slot Creation</option><option>Booking Open</option><option>Closed</option><option>Completed</option></select>
          <button class="btn btn-primary" :disabled="busy || loading || !!exam.published_at" @click="changeStatus">Update Phase</button>
          <button class="btn btn-outline-primary" :disabled="busy || loading || !!exam.published_at" @click="editing = true">Edit Examination</button>
          <button v-if="!exam.published_at" class="btn btn-success" :disabled="busy || loading || exam.status !== 'Completed'" @click="publish">Publish Results</button>
          <button class="btn btn-outline-danger" :disabled="busy || loading" @click="archive">Archive</button>
        </div>
      </section>
      <section class="card mb-4">
        <div class="card-header"><h2>Evaluation Rubric</h2><button v-if="role === 'Admin'" class="btn btn-create" @click="openRubrics">Manage Rubric</button></div>
        <div class="table-responsive"><table class="table drive-table"><thead><tr><th>Criterion</th><th>Description</th><th>Maximum Marks</th><th>Weightage</th></tr></thead><tbody><tr v-for="rubric in exam.rubrics" :key="rubric.id"><td>{{ rubric.name }}</td><td>{{ rubric.description }}</td><td>{{ rubric.maximum_marks }}</td><td>{{ rubric.weightage }}%</td></tr><tr v-if="!exam.rubrics.length"><td colspan="4" class="empty-text">No rubric configured yet.</td></tr></tbody></table></div>
      </section>
      <section class="card">
        <div class="card-header"><h2>Examination Slots</h2><RouterLink v-if="role !== 'Student'" :to="`${base}/slots`" class="btn btn-create">Manage Slots</RouterLink><button v-else class="btn btn-outline-primary" @click="load">Refresh</button></div>
        <div v-if="role === 'Student' && myBooking" class="alert alert-info">You already have a {{ myBooking.status.toLowerCase() }} booking for this examination. <RouterLink to="/student/bookings">View booking</RouterLink></div>
        <div class="table-responsive"><table class="table drive-table"><thead><tr><th>Examiner</th><th>Start / End</th><th>Location</th><th>Available Seats</th><th>Status</th><th v-if="role === 'Student'">Action</th></tr></thead><tbody><tr v-for="slot in slots" :key="slot.id"><td>{{ slot.examiner }}</td><td>{{ formatDate(slot.start) }}<small class="d-block text-secondary">{{ formatDate(slot.end) }}</small></td><td>{{ slot.location || "Online / To be confirmed" }}</td><td>{{ slot.available_seats }} / {{ slot.capacity }}</td><td><span class="badge" :class="statusClass(slot.status)">{{ slot.status }}</span></td><td v-if="role === 'Student'"><button class="btn btn-sm action view" :disabled="busy || !!myBooking || !canBook(slot)" @click="book(slot)">Book Slot</button></td></tr><tr v-if="!slots.length"><td colspan="6" class="empty-text">No slots have been created yet.</td></tr></tbody></table></div>
      </section>
    </template>
    <p v-else-if="!error" class="loading-text">Loading examination details...</p>
    <ExamForm v-if="editing" :exam="exam" @close="editing = false" @saved="editing = false; message = 'Examination saved.'; load()" />
    <Modal v-if="rubrics" title="Manage Evaluation Rubric" :busy="busy" @close="rubrics = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <form @submit.prevent="saveRubrics">
        <fieldset v-for="(row, index) in rubrics" :key="index" class="rubric-editor"><legend class="h6">Criterion {{ index + 1 }}</legend><label :for="`criterion-${index}`" class="form-label">Criterion name</label><input :id="`criterion-${index}`" v-model="row.name" class="form-control mb-3" required maxlength="120" /><div class="row g-3"><div class="col-6"><label :for="`max-${index}`" class="form-label">Maximum marks</label><input :id="`max-${index}`" v-model.number="row.maximum_marks" type="number" min="1" max="1000" step="0.01" class="form-control" required /></div><div class="col-6"><label :for="`weight-${index}`" class="form-label">Weightage (%)</label><input :id="`weight-${index}`" v-model.number="row.weightage" type="number" min="0.01" max="100" step="0.01" class="form-control" required /></div></div><label :for="`description-${index}`" class="form-label mt-3">Description</label><textarea :id="`description-${index}`" v-model="row.description" class="form-control" rows="2" maxlength="1000"></textarea><button type="button" class="btn btn-sm btn-outline-danger mt-3" :disabled="rubrics.length === 1" @click="rubrics.splice(index, 1)">Remove criterion</button></fieldset>
        <div class="d-flex justify-content-between align-items-center"><button type="button" class="btn btn-outline-primary" :disabled="rubrics.length >= 30" @click="rubrics.push({ name: '', maximum_marks: 10, weightage: 0, description: '' })">+ Add Criterion</button><strong>Total: {{ rubricTotal }}%</strong></div>
        <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="rubrics = null">Cancel</button><button class="btn btn-primary" :disabled="busy || rubricTotal !== 100">Save Rubric</button></div>
      </form>
    </Modal>
  </div>
</template>
<script>
import { api, session, formatDate, statusClass } from "../services/api";
import Modal from "./Modal.vue";
import ExamForm from "./ExamForm.vue";
export default {
  components: { Modal, ExamForm },
  data: () => ({ exam: null, slots: [], myBooking: null, error: "", message: "", modalError: "", busy: false, loading: false, nextStatus: "", editing: false, rubrics: null }),
  computed: { role() { return session.user.role; }, base() { return `/${this.role.toLowerCase()}`; }, rubricTotal() { return Math.round(this.rubrics.reduce((sum, row) => sum + (Number(row.weightage) || 0), 0) * 100) / 100; } },
  mounted() { this.load(); },
  methods: {
    formatDate, statusClass,
    async load() {
      this.error = ""; this.loading = true;
      try {
        const id = Number(this.$route.params.id);
        const [exams, slots] = await Promise.all([api("/examinations"), api(`/examinations/${id}/slots`)]);
        this.exam = exams.items.find(e => e.id === id);
        if (!this.exam) throw new Error("Examination not found or access is not permitted.");
        this.nextStatus = this.exam.status; this.slots = slots.items;
        if (this.role === "Student") this.myBooking = (await api(`/student/bookings?exam_id=${id}`)).items.find(b => b.status !== "Cancelled");
      } catch (e) { this.error = e.message; } finally { this.loading = false; }
    },
    canBook(slot) { const time = Date.now(); return !this.exam.archived && this.exam.status === "Booking Open" && time >= Date.parse(this.exam.booking_start) && time < Date.parse(this.exam.booking_end) && slot.status === "Available" && slot.available_seats > 0; },
    async action(path, body) {
      this.busy = true; this.error = ""; this.message = "";
      try { this.message = (await api(path, { method: "POST", body })).message || "Booking confirmed."; await this.load(); }
      catch (e) { this.error = e.message; } finally { this.busy = false; }
    },
    changeStatus() { this.action(`/admin/examinations/${this.exam.id}/status`, { status: this.nextStatus }); },
    publish() { if (window.confirm("Publish examination results? Students will immediately see their marks and remarks. Published results cannot be edited.")) this.action(`/admin/examinations/${this.exam.id}/publish`); },
    book(slot) { if (window.confirm(`Confirm booking for ${this.exam.name} with ${slot.examiner} on ${formatDate(slot.start)}?`)) this.action("/student/bookings", { slot_id: slot.id }); },
    async archive() { if (!window.confirm("Archive this examination? Its full history will be preserved.")) return; try { await api(`/admin/examinations/${this.exam.id}`, { method: "DELETE" }); this.message = "Examination archived."; await this.load(); } catch (e) { this.error = e.message; } },
    openRubrics() { this.modalError = ""; this.rubrics = this.exam.rubrics.length ? this.exam.rubrics.map(r => ({ ...r })) : [{ name: "", maximum_marks: 100, weightage: 100, description: "" }]; },
    async saveRubrics() {
      this.busy = true; this.modalError = "";
      try { await api(`/admin/examinations/${this.exam.id}/rubrics`, { method: "PUT", body: { criteria: this.rubrics } }); this.rubrics = null; this.message = "Rubric saved."; await this.load(); }
      catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
  },
};
</script>
