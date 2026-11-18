import { createRouter, createWebHistory } from "vue-router";
import { restoreSession, session } from "../services/api";
import Login from "../components/Login.vue";
import StuReg from "../components/StuReg.vue";
import AppShell from "../components/AppShell.vue";
import Dashboard from "../components/Dashboard.vue";
import AdmCourses from "../components/AdmCourses.vue";
import AdmUsers from "../components/AdmUsers.vue";
import Examinations from "../components/Examinations.vue";
import ExamDetails from "../components/ExamDetails.vue";
import Slots from "../components/Slots.vue";
import Bookings from "../components/Bookings.vue";
import Reports from "../components/Reports.vue";

const routes = [
  { path: "/", component: Login, meta: { title: "Login" } },
  { path: "/student-registration", component: StuReg, meta: { title: "Student registration" } },
];
for (const role of ["Admin", "Examiner", "Student"]) {
  const base = role.toLowerCase();
  const children = [
    { path: "home", component: Dashboard, meta: { title: `${role} dashboard` } },
    { path: "examinations", component: Examinations, meta: { title: "Examinations" } },
    { path: "examinations/:id", component: ExamDetails, meta: { title: "Examination details" } },
    { path: "bookings", component: Bookings, meta: { title: role === "Examiner" ? "Booked students" : "Bookings" } },
  ];
  if (role !== "Student") children.push(
    { path: "slots", component: Slots, meta: { title: "Examination slots" } },
  );
  if (role === "Admin") children.push(
    { path: "courses", component: AdmCourses, meta: { title: "Courses" } },
    { path: "examiners", component: AdmUsers, props: { userRole: "Examiner" }, meta: { title: "Examiners" } },
    { path: "students", component: AdmUsers, props: { userRole: "Student" }, meta: { title: "Students" } },
    { path: "reports", component: Reports, meta: { title: "Monthly report" } },
  );
  if (role === "Student") children.push(
    { path: "history", component: Bookings, props: { mode: "history" }, meta: { title: "Examination history" } },
  );
  routes.push({ path: `/${base}`, component: AppShell, meta: { role }, redirect: `/${base}/home`, children });
}
routes.push({ path: "/:pathMatch(.*)*", redirect: "/" });
const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) });
router.beforeEach(async (to) => {
  if (!session.loaded) {
    try {
      await restoreSession();
    } catch {
      if (to.path !== "/") return "/";
    }
  }
  if (to.meta.role && !session.user) return "/";
  if (to.meta.role && session.user.role !== to.meta.role) return `/${session.user.role.toLowerCase()}/home`;
  if (to.path === "/" && session.user) return `/${session.user.role.toLowerCase()}/home`;
  document.title = `${to.meta.title || "Portal"} | Exortal`;
});
export default router;
