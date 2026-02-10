import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";



const router = createRouter({
    history: createWebHistory("/"),
    routes: [
        {
            path: "/",
            name: "home",
            component: HomeView,
        },
        {
            path: "/clases",
            name: "clases",
            component: () => import("../views/SeleccionClase.vue")
        }
    ]
});

export default router;
