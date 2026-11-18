<template>
  <main class="login">
    <div class="comregbx">
      <div class="text"><div class="login-brand">Exortal<span class="brand-square"></span></div><h1>Student Registration</h1></div>
      <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
      <div v-if="success" class="alert alert-success" role="status">{{ success }} <RouterLink to="/">Go to login</RouterLink></div>
      <form v-else @submit.prevent="register">
        <div class="row g-3">
          <div class="col-md-6"><label for="name" class="form-label">Full name</label><input id="name" v-model="form.name" class="form-control" required maxlength="120" autocomplete="name" /></div>
          <div class="col-md-6"><label for="roll" class="form-label">Roll number</label><input id="roll" v-model="form.roll_number" class="form-control" required maxlength="40" /></div>
          <div class="col-12"><label for="email" class="form-label">Email address</label><input id="email" v-model="form.email" type="email" class="form-control" required maxlength="254" autocomplete="email" /></div>
          <div class="col-md-6"><label for="department" class="form-label">Department</label><input id="department" v-model="form.department" class="form-control" required maxlength="100" /></div>
          <div class="col-md-6"><label for="phone" class="form-label">Phone number</label><input id="phone" v-model="form.phone" type="tel" class="form-control" required maxlength="30" autocomplete="tel" /></div>
          <div class="col-12"><label for="password" class="form-label">Password</label><input id="password" v-model="form.password" type="password" class="form-control" required autocomplete="new-password" /></div>
          <div class="col-12"><label for="confirm" class="form-label">Confirm password</label><input id="confirm" v-model="confirm" type="password" class="form-control" required autocomplete="new-password" /></div>
        </div>
        <div class="ele"><button class="btn btn-primary login-btn" :disabled="busy">{{ busy ? "Creating account..." : "Register" }}</button></div>
      </form>
      <div class="Next">Already registered? <RouterLink to="/">Login</RouterLink></div>
    </div>
  </main>
</template>
<script>
import { api } from "../services/api";
import "../assets/login.css";
export default {
  data: () => ({ form: { name: "", roll_number: "", email: "", department: "", phone: "", password: "" }, confirm: "", busy: false, error: "", success: "" }),
  methods: {
    async register() {
      this.error = "";
      if (this.form.password !== this.confirm) { this.error = "Passwords do not match."; return; }
      this.busy = true;
      try { this.success = (await api("/student/register", { method: "POST", body: this.form })).message; }
      catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
