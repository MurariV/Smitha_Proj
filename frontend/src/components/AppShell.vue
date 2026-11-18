<template>
  <div class="dashboard">
    <a href="#page-main" class="visually-hidden-focusable skip-link">Skip to content</a>
    <header class="navbar exortal-navbar">
      <RouterLink :to="`${base}/home`" class="logo-section"><span class="logo-word">Exortal<span class="brand-square"></span></span><span class="role-title">{{ session.user?.role === "Admin" ? "Administration" : session.user?.role + " Portal" }}</span></RouterLink>
      <div class="nav-buttons">
        <RouterLink v-if="$route.path !== `${base}/home`" :to="`${base}/home`" class="btn btn-edit">Home</RouterLink>
        <button v-if="session.user?.role === 'Student'" class="btn btn-edit" @click="openProfile">Edit Profile</button>
        <RouterLink v-if="session.user?.role === 'Student' && $route.path !== '/student/history'" to="/student/history" class="btn btn-edit">Examination History</RouterLink>
        <button class="btn btn-logout" :disabled="busy" @click="logout">Logout</button>
      </div>
    </header>
    <main id="page-main" class="page-content">
      <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
      <RouterView v-if="session.user" :key="$route.path" />
    </main>
    <Modal v-if="showProfile" title="My Profile" :busy="busy" @close="showProfile = false">
      <div v-if="modalError" class="alert alert-danger" role="alert">{{ modalError }}</div>
      <p class="text-secondary">{{ session.user.email }} &middot; {{ session.user.role }} <span v-if="session.user.roll_number">&middot; {{ session.user.roll_number }}</span></p>
      <form @submit.prevent="saveProfile">
        <label class="form-label" for="profile-name">Full name</label><input id="profile-name" v-model="profile.name" class="form-control mb-3" required maxlength="120" />
        <label class="form-label" for="profile-department">Department</label><input id="profile-department" v-model="profile.department" class="form-control mb-3" required maxlength="100" />
        <label class="form-label" for="profile-phone">Phone number</label><input id="profile-phone" v-model="profile.phone" class="form-control mb-3" type="tel" required maxlength="30" />
        <div class="popup-buttons"><button type="button" class="btn btn-secondary" :disabled="busy" @click="showProfile = false">Cancel</button><button class="btn btn-primary" :disabled="busy">Save profile</button></div>
      </form>
    </Modal>
  </div>
</template>
<script>
import { api, session } from "../services/api";
import Modal from "./Modal.vue";
export default {
  components: { Modal },
  data: () => ({ session, error: "", modalError: "", busy: false, showProfile: false, profile: {} }),
  computed: {
    base() { return `/${this.session.user?.role.toLowerCase()}`; },
  },
  methods: {
    openProfile() { this.profile = { name: session.user.name, department: session.user.department, phone: session.user.phone }; this.modalError = ""; this.showProfile = true; },
    async saveProfile() {
      this.busy = true; this.modalError = "";
      try { session.user = (await api("/profile", { method: "PUT", body: this.profile })).user; this.showProfile = false; }
      catch (error) { this.modalError = error.message; }
      finally { this.busy = false; }
    },
    async logout() {
      this.busy = true;
      try { await api("/logout", { method: "POST" }); session.user = null; await this.$router.push("/"); }
      catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
  },
};
</script>
