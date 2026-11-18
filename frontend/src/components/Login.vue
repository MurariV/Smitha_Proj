<template>
  <main class="login">
    <div class="lbox">
      <div class="text">
        <div class="login-brand">Exortal<span class="brand-square"></span></div>
        <h1>Login</h1>
      </div>
      <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
      <form @submit.prevent="loginUser">
        <div class="input">
          <label for="email" class="form-label">Email address</label>
          <input id="email" v-model="email" type="email" class="form-control" autocomplete="username" placeholder="Enter your email address" required maxlength="254" />
        </div>
        <div class="input">
          <label for="password" class="form-label">Password</label>
          <input id="password" v-model="password" type="password" class="form-control" autocomplete="current-password" placeholder="Enter your password" required />
        </div>
        <div class="ele"><button class="btn btn-primary login-btn" :disabled="busy">{{ busy ? "Logging in..." : "Login" }}</button></div>
        <div class="Next">New to Exortal? <RouterLink to="/student-registration">Student registration</RouterLink></div>
      </form>
    </div>
  </main>
</template>
<script>
import { api, session } from "../services/api";
import "../assets/login.css";
export default {
  data: () => ({ email: "", password: "", error: "", busy: false }),
  methods: {
    async loginUser() {
      this.busy = true; this.error = "";
      try {
        const result = await api("/login", { method: "POST", body: { email: this.email, password: this.password } });
        session.user = result.user; session.loaded = true;
        await this.$router.push(`/${result.user.role.toLowerCase()}/home`);
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
