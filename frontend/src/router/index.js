import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import SeleccionClase from "../views/SeleccionClase.vue";



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
            component: SeleccionClase,
        }
    ]
});

export default router;
