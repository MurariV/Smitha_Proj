<template>
  <Modal :title="exam ? 'Edit Examination' : 'Create Examination'" :busy="busy" @close="$emit('close')">
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <form @submit.prevent="save">
      <div class="row g-3">
        <div class="col-12"><label for="exam-course" class="form-label">Course</label><select id="exam-course" v-model.number="form.course_id" class="form-select" required><option disabled value="">Select a course</option><option v-for="course in courses.filter(c => c.status === 'Active')" :key="course.id" :value="course.id">{{ course.code }} - {{ course.name }}</option></select></div>
        <div class="col-12"><label for="exam-name" class="form-label">Examination name</label><input id="exam-name" v-model="form.name" class="form-control" required maxlength="160" /></div>
        <div class="col-md-4"><label for="exam-type" class="form-label">Type</label><select id="exam-type" v-model="form.exam_type" class="form-select"><option>Viva</option><option>Practical</option><option>Project Demo</option><option>Assessment</option></select></div>
        <div class="col-md-4"><label for="exam-duration" class="form-label">Duration (minutes)</label><input id="exam-duration" v-model.number="form.duration" class="form-control" type="number" min="5" max="480" required /></div>
        <div class="col-md-4"><label for="exam-marks" class="form-label">Maximum marks</label><input id="exam-marks" v-model.number="form.maximum_marks" class="form-control" type="number" min="1" max="1000" step="0.01" required /></div>
        <div class="col-12"><h3 class="h6 mt-2 mb-0">Examination Timeline</h3></div>
        <div v-for="field in dates" :key="field.key" class="col-md-6"><label :for="field.key" class="form-label">{{ field.label }}</label><input :id="field.key" v-model="form[field.key]" type="datetime-local" class="form-control" required /></div>
        <div class="col-12"><label for="exam-examiners" class="form-label">Assigned examiners</label><select id="exam-examiners" v-model="form.examiner_ids" multiple class="form-select" required size="3"><option v-for="user in examiners.filter(e => e.status === 'Active')" :key="user.id" :value="user.examiner_id">{{ user.name }} - {{ user.department }}</option></select><small class="text-secondary">Select one or more examiners (Ctrl/Cmd + click).</small></div>
        <div class="col-12"><label for="exam-instructions" class="form-label">Examination instructions</label><textarea id="exam-instructions" v-model="form.instructions" class="form-control" rows="3" maxlength="5000"></textarea></div>
      </div>
      <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="$emit('close')">Cancel</button><button class="btn btn-primary" :disabled="busy">Save Examination</button></div>
    </form>
  </Modal>
</template>
<script>
import { api, toISO, toLocalInput } from "../services/api";
import Modal from "./Modal.vue";
const dates = [{ key: "slot_creation_start", label: "Slot creation starts" }, { key: "slot_creation_end", label: "Slot creation ends" }, { key: "booking_start", label: "Student booking starts" }, { key: "booking_end", label: "Student booking ends" }];
export default {
  components: { Modal }, props: { exam: Object }, emits: ["close", "saved"],
  data: () => ({ form: { course_id: "", name: "", exam_type: "Viva", duration: 30, maximum_marks: 100, instructions: "", examiner_ids: [] }, dates, courses: [], examiners: [], error: "", busy: false }),
  async mounted() {
    if (this.exam) {
      this.form = { ...this.exam, examiner_ids: this.exam.examiners.map(e => e.id) };
      for (const field of dates) this.form[field.key] = toLocalInput(this.exam[field.key]);
    }
    try { const [courses, examiners] = await Promise.all([api("/admin/courses"), api("/admin/users?role=Examiner")]); this.courses = courses.items; this.examiners = examiners.items; }
    catch (error) { this.error = error.message; }
  },
  methods: {
    async save() {
      this.error = ""; this.busy = true;
      try {
        const payload = { ...this.form };
        for (const field of dates) payload[field.key] = toISO(payload[field.key]);
        await api(`/admin/examinations${this.exam ? `/${this.exam.id}` : ""}`, { method: this.exam ? "PUT" : "POST", body: payload });
        this.$emit("saved");
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
