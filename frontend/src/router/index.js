import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import ModeloImagenes from "../views/ModeloImagenes.vue";



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
            component: ModeloImagenes,
        }
    ]
});

export default router;
