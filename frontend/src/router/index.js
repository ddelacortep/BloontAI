import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import ModeloImagenes from "../views/ModeloImagenes.vue";
import SeleccionModelo from "@/views/SeleccionModelo.vue";



const router = createRouter({
    history: createWebHistory("/"),
    routes: [
        {
            path: "/",
            name: "home",
            component: HomeView,
        },
        {
            path: "/modelo-imagenes",
            name: "modelo-imagenes",
            component: ModeloImagenes,
        },
        {
            path: "/seleccion-modelo",
            name: "seleccion-modelo",
            component: SeleccionModelo,
        }
    ]
});

export default router;
