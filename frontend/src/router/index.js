import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import ModeloImagenes from "../views/ModeloImagenes.vue";
import ModeloTexto from "@/views/ModeloTexto.vue";
import SeleccionModelo from "@/views/SeleccionModelo.vue";
import ModeloAudio from "@/views/ModeloAudio.vue";



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
            path: "/modelo-texto",
            name: "modelo-texto",
            component: ModeloTexto,
        },
        {
            path: "/seleccion-modelo",
            name: "seleccion-modelo",
            component: SeleccionModelo,
        },
        {
            path: "/modelo-audio",
            name: "modelo-audio",
            component: ModeloAudio,
        },
    ]
});

export default router;
