<template>
  <section class="card">
    <div class="card-header"><h1>{{ userRole }}s</h1><button v-if="userRole === 'Examiner'" class="btn btn-create" @click="edit()">+ Add Examiner</button></div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div><div v-if="message" class="alert alert-success" role="status">{{ message }}</div>
    <form class="toolbar" @submit.prevent="load"><input v-model="search" aria-label="Search users" class="form-control search-input" placeholder="Search by name, email or roll number..." /><button class="btn btn-primary">Search</button></form>
    <div class="table-responsive"><table class="table drive-table"><thead><tr><th>ID</th><th>Name</th><th>Contact</th><th>Department</th><th v-if="userRole === 'Student'">Roll Number</th><th>Status</th><th>Action</th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td>{{ userRole === "Student" ? user.student_id : user.examiner_id }}</td><td><strong>{{ user.name }}</strong></td><td>{{ user.email }}<small class="d-block text-secondary">{{ user.phone }}</small></td><td>{{ user.department }}</td><td v-if="userRole === 'Student'">{{ user.roll_number }}</td><td><span class="badge" :class="statusClass(user.status)">{{ user.status }}</span></td><td><button class="btn btn-sm action view" @click="edit(user)">View / Manage</button></td></tr><tr v-if="!users.length"><td colspan="7" class="empty-text">No {{ userRole.toLowerCase() }}s found.</td></tr></tbody></table></div>
    <Modal v-if="form" :title="`${form.id ? 'Manage' : 'Add'} ${userRole}`" :busy="busy" @close="form = null">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <form @submit.prevent="save"><div class="row g-3">
        <div class="col-12"><label for="user-name" class="form-label">Name</label><input id="user-name" v-model="form.name" class="form-control" required maxlength="120" /></div>
        <div class="col-12"><label for="user-email" class="form-label">Email address</label><input id="user-email" v-model="form.email" type="email" class="form-control" :disabled="!!form.id" required maxlength="254" /></div>
        <div class="col-md-6"><label for="user-department" class="form-label">Department</label><input id="user-department" v-model="form.department" class="form-control" required maxlength="100" /></div>
        <div class="col-md-6"><label for="user-phone" class="form-label">Phone number</label><input id="user-phone" v-model="form.phone" class="form-control" type="tel" required maxlength="30" /></div>
        <div v-if="form.id" class="col-12"><label for="user-status" class="form-label">Account status</label><select id="user-status" v-model="form.status" class="form-select"><option>Active</option><option>Inactive</option></select></div>
        <div v-if="!form.id" class="col-12"><label for="user-password" class="form-label">Password</label><input id="user-password" v-model="form.password" type="password" class="form-control" required autocomplete="new-password" /></div>
      </div><div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="form = null">Cancel</button><button class="btn btn-primary" :disabled="busy">Save {{ userRole }}</button></div></form>
    </Modal>
  </section>
</template>
<script>
import { api, statusClass } from "../services/api";
import Modal from "./Modal.vue";
export default {
  components: { Modal }, props: { userRole: String },
  data: () => ({ users: [], search: "", form: null, busy: false, error: "", modalError: "", message: "" }),
  mounted() { this.load(); },
  methods: {
    statusClass,
    async load() { this.error = ""; try { this.users = (await api(`/admin/users?role=${this.userRole}&q=${encodeURIComponent(this.search)}`)).items; } catch (e) { this.error = e.message; } },
    edit(user) { this.form = user ? { ...user } : { name: "", email: "", department: "", phone: "", password: "", status: "Active" }; this.modalError = ""; },
    async save() {
      this.busy = true; this.modalError = "";
      try { await api(`/admin/users${this.form.id ? `/${this.form.id}` : ""}`, { method: this.form.id ? "PUT" : "POST", body: this.form }); this.form = null; this.message = `${this.userRole} saved.`; await this.load(); }
      catch (e) { this.modalError = e.message; } finally { this.busy = false; }
    },
  },
};
</script>
