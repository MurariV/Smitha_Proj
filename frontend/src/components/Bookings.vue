<template>
  <section class="card">
    <div class="card-header"><h1>{{ title }}</h1><button v-if="mode === 'history'" class="btn btn-create" :disabled="busy" @click="exportHistory">Download CSV</button><button v-else class="btn btn-outline-primary" @click="load">Refresh</button></div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <div class="toolbar"><input v-model="search" aria-label="Search bookings" class="form-control search-input" placeholder="Search student, examination, examiner or booking ID..." /><select v-model="filter" aria-label="Filter booking status" class="form-select filter-select"><option value="">All statuses</option><option>Booked</option><option>Completed</option><option>Cancelled</option></select></div>
    <div class="table-responsive"><table class="table drive-table"><thead><tr><th>ID</th><th v-if="role !== 'Student'">Student</th><th>Examination</th><th>Examiner / Schedule</th><th>Status</th><th v-if="role === 'Student'">Marks</th><th v-if="mode === 'history'">Remarks</th><th>Action</th></tr></thead><tbody>
      <tr v-for="booking in filtered" :key="booking.id">
        <td>#{{ booking.id }}</td><td v-if="role !== 'Student'"><strong>{{ booking.student }}</strong><small class="d-block text-secondary">{{ booking.roll_number }}</small></td>
        <td>{{ booking.slot.examination }}<small class="d-block text-secondary">{{ booking.slot.course }}</small></td>
        <td>{{ booking.slot.examiner }}<small class="d-block text-secondary">{{ formatDate(booking.slot.start) }}</small></td>
        <td><span class="badge" :class="statusClass(booking.status)">{{ booking.status }}</span></td>
        <td v-if="role === 'Student'">{{ booking.evaluation ? `${booking.evaluation.total_marks} / ${booking.maximum_marks}` : "-" }}</td>
        <td v-if="mode === 'history'">{{ booking.evaluation?.remarks || "-" }}</td>
        <td class="actions-cell">
          <button class="btn btn-sm action view" @click="selected = booking">View Details</button>
          <button v-if="role === 'Student' && booking.status === 'Booked'" class="btn btn-sm action delete" :disabled="busy || Date.now() >= Date.parse(booking.slot.booking_end)" @click="cancel(booking)">Cancel</button>
          <button v-if="role === 'Examiner' && booking.status === 'Booked'" class="btn btn-sm action done" :disabled="busy || Date.now() < Date.parse(booking.slot.start)" @click="openEvaluation(booking)">Evaluate</button>
          <button v-if="role === 'Admin' && booking.status === 'Booked'" class="btn btn-sm btn-outline-primary" @click="openReschedule(booking)">Reschedule</button>
        </td>
      </tr>
      <tr v-if="!filtered.length"><td colspan="7" class="empty-text">{{ loading ? "Loading bookings..." : "No bookings found." }}</td></tr>
    </tbody></table></div>
    <Modal v-if="selected" :title="selected.evaluation ? 'Examination Result' : 'Booking Details'" @close="selected = null">
      <div class="scorecard">
        <div class="result-heading"><h3>{{ selected.slot.examination }}</h3><p>{{ selected.student }} &middot; {{ selected.roll_number }}</p></div>
        <dl class="detail-list"><div><dt>Booking ID</dt><dd>#{{ selected.id }}</dd></div><div><dt>Course</dt><dd>{{ selected.slot.course }}</dd></div><div><dt>Examiner</dt><dd>{{ selected.slot.examiner }}</dd></div><div><dt>Schedule</dt><dd>{{ formatDate(selected.slot.start) }} - {{ formatDate(selected.slot.end) }}</dd></div><div><dt>Location</dt><dd>{{ selected.slot.location || "To be confirmed" }}</dd></div><div><dt>Booking status</dt><dd>{{ selected.status }}</dd></div><div><dt>Booked on</dt><dd>{{ formatDate(selected.booked_at) }}</dd></div></dl>
        <a v-if="selected.slot.meeting_link" :href="selected.slot.meeting_link" target="_blank" rel="noopener noreferrer" class="btn btn-outline-primary mb-3">Open Meeting Link</a>
        <template v-if="selected.evaluation"><div class="score-banner"><span>Total Marks</span><strong>{{ selected.evaluation.total_marks }} / {{ selected.maximum_marks }}</strong><span>{{ selected.published ? "Published result" : "Not yet published to student" }}</span></div><div class="table-responsive mt-3"><table class="table"><thead><tr><th>Criterion</th><th>Score</th><th>Weight</th></tr></thead><tbody><tr v-for="score in selected.evaluation.scores" :key="score.rubric_id"><td>{{ score.criterion }}</td><td>{{ score.marks }} / {{ score.maximum_marks }}</td><td>{{ score.weightage }}%</td></tr></tbody></table></div><h3 class="h6">Examiner Feedback</h3><p class="preserve-lines">{{ selected.evaluation.remarks || "No additional remarks." }}</p><p class="small text-secondary">Evaluated {{ formatDate(selected.evaluation.evaluated_at) }}</p></template>
        <div v-else-if="selected.status === 'Completed'" class="alert alert-info">Evaluation submitted. Marks and feedback are visible after publication.</div>
      </div><div class="popup-buttons"><button class="btn btn-primary" @click="selected = null">Close</button></div>
    </Modal>
    <Modal v-if="evaluation" title="Evaluate Student" :busy="busy" @close="evaluation = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <h3 class="h5">{{ evaluation.booking.student }}</h3><p>{{ evaluation.booking.slot.examination }}</p>
      <form @submit.prevent="submitEvaluation">
        <div v-for="score in evaluation.scores" :key="score.rubric_id" class="rubric-editor"><label :for="`score-${score.rubric_id}`" class="form-label">{{ score.name }} <small>({{ score.weightage }}% weight)</small></label><p class="small text-secondary">{{ score.description }}</p><div class="input-group"><input :id="`score-${score.rubric_id}`" v-model.number="score.marks" class="form-control" type="number" min="0" :max="score.maximum_marks" step="0.01" required /><span class="input-group-text">/ {{ score.maximum_marks }}</span></div></div>
        <label for="evaluation-remarks" class="form-label">Remarks and feedback</label><textarea id="evaluation-remarks" v-model="evaluation.remarks" class="form-control" rows="4" maxlength="5000"></textarea>
        <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="evaluation = null">Cancel</button><button class="btn btn-primary" :disabled="busy || !evaluation.scores.length">Submit Evaluation</button></div>
      </form>
    </Modal>
    <Modal v-if="reschedule" title="Reschedule Booking" :busy="busy" @close="reschedule = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div><p>{{ reschedule.booking.student }} &middot; {{ reschedule.booking.slot.examination }}</p>
      <form @submit.prevent="saveReschedule"><label for="target-slot" class="form-label">New examination slot</label><select id="target-slot" v-model.number="reschedule.slot_id" class="form-select" required><option value="" disabled>Select a different slot</option><option v-for="slot in reschedule.slots" :key="slot.id" :value="slot.id">#{{ slot.id }} - {{ slot.examiner }} - {{ formatDate(slot.start) }} ({{ slot.available_seats }} seats)</option></select><p v-if="!reschedule.slots.length" class="text-warning mt-2">No alternate slots with capacity are available for this examination.</p><label for="reschedule-reason" class="form-label mt-3">Reason for exceptional change</label><textarea id="reschedule-reason" v-model="reschedule.reason" class="form-control" required maxlength="1000" rows="3"></textarea><div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="reschedule = null">Cancel</button><button class="btn btn-primary" :disabled="busy || !reschedule.slots.length">Reschedule Booking</button></div></form>
    </Modal>
  </section>
</template>
<script>
import { api, API_BASE, session, formatDate, statusClass } from "../services/api";
import Modal from "./Modal.vue";
export default {
  components: { Modal }, props: { mode: { type: String, default: "bookings" } },
  emits: ["changed"],
  data: () => ({ items: [], search: "", filter: "", selected: null, evaluation: null, reschedule: null, loading: false, busy: false, error: "", modalError: "", message: "", downloadCancelled: false }),
  computed: {
    role() { return session.user.role; },
    title() { return this.mode === "history" ? "Examination History" : this.role === "Examiner" ? "Booked Students" : this.role === "Student" ? "My Bookings" : "All Bookings"; },
    filtered() {
      return this.items.filter(b => (!this.filter || b.status === this.filter)
        && `${b.id} ${b.student} ${b.roll_number} ${b.slot.examination} ${b.slot.examiner}`.toLowerCase().includes(this.search.toLowerCase()));
    },
  },
  mounted() { this.load(); },
  beforeUnmount() { this.downloadCancelled = true; },
  methods: {
    formatDate, statusClass,
    async load() { this.loading = true; this.error = ""; try { this.items = (await api(`/${this.role.toLowerCase()}/bookings`)).items; } catch (e) { this.error = e.message; } finally { this.loading = false; } },
    async cancel(booking) {
      if (!window.confirm(`Cancel your booking for ${booking.slot.examination}?`)) return;
      this.busy = true;
      try { this.message = (await api(`/student/bookings/${booking.id}/cancel`, { method: "POST" })).message; await this.load(); this.$emit("changed"); } catch (e) { this.error = e.message; } finally { this.busy = false; }
    },
    async openEvaluation(booking) {
      this.error = ""; this.modalError = "";
      try { const rubrics = (await api(`/examinations/${booking.exam_id}/rubrics`)).items; this.evaluation = { booking, remarks: "", scores: rubrics.map(r => ({ ...r, rubric_id: r.id, marks: "" })) }; }
      catch (e) { this.error = e.message; }
    },
    async submitEvaluation() {
      if (!window.confirm("Submit these marks and remarks? This evaluation cannot be edited after submission.")) return;
      this.busy = true; this.modalError = "";
      try { this.message = (await api(`/examiner/bookings/${this.evaluation.booking.id}/evaluate`, { method: "POST", body: { scores: this.evaluation.scores.map(r => ({ rubric_id: r.rubric_id, marks: r.marks })), remarks: this.evaluation.remarks } })).message; this.evaluation = null; await this.load(); this.$emit("changed"); }
      catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
    async openReschedule(booking) {
      this.error = ""; this.modalError = "";
      try { const slots = (await api(`/examinations/${booking.exam_id}/slots`)).items; this.reschedule = { booking, slot_id: "", reason: "", slots: slots.filter(s => s.id !== booking.slot_id && s.status === "Available" && s.available_seats > 0 && Date.parse(s.start) > Date.now()) }; }
      catch (e) { this.error = e.message; }
    },
    async saveReschedule() {
      this.busy = true; this.modalError = "";
      try { this.message = (await api(`/admin/bookings/${this.reschedule.booking.id}/reschedule`, { method: "POST", body: { slot_id: this.reschedule.slot_id, reason: this.reschedule.reason } })).message; this.reschedule = null; await this.load(); this.$emit("changed"); }
      catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
    async exportHistory() {
      this.busy = true; this.error = ""; this.message = "";
      try {
        let job = await api("/student/exports", { method: "POST" });
        const id = job.id;
        const deadline = Date.now() + 120000;
        while (job.status !== "Completed") {
          if (job.status === "Failed") throw new Error(job.error || "CSV export failed. Please retry.");
          if (Date.now() >= deadline) throw new Error("CSV is not ready. Check the Celery worker and try Download again.");
          await new Promise(resolve => setTimeout(resolve, 1000));
          if (this.downloadCancelled) return;
          const result = await api("/student/exports");
          job = result.items.find(item => item.id === id);
          if (!job) throw new Error("This export was replaced. Please retry.");
        }
        if (!this.downloadCancelled) window.location.assign(`${API_BASE}/student/exports/${id}/download`);
      } catch (e) { this.error = e.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
