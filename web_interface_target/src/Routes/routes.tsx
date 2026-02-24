import { ReactElement } from "react";
import CommunityFeed from "Pages/CommunityFeed";
import Dashboard from "Pages/Home/index";
import CommunityDetails from "Pages/CommunityDetails";
import ManageSubscription from "Pages/ManageSubscription";
import Chatbot from "Pages/Chatbot";
import ImageGenerator from "Pages/ImageGenerator";
import VoiceGenerator from "Pages/VoiceGenerator";
import Register from "Pages/Auth/Register";
import Faq from "Pages/Settings/Faq";
import Login from "Pages/Auth/Login";
import ResetPassword from "Pages/Auth/ResetPassword";
import LinksList from "../Pages/LinksList";
import LenieLink from "../Pages/Documents/Links";

export interface RouteProps {
    path: string;
    component: ReactElement;
}

const routes: RouteProps[] = [
    { path: "/", component: <Dashboard /> },
    { path: "/links-list", component: <LinksList /> },
    { path: "/link", component: <LenieLink /> },
    { path: "/link/:id?", component: <LenieLink /> },

    { path: "/community-feed", component: <CommunityFeed /> },
    { path: "/community-details", component: <CommunityDetails /> },
    { path: "/manage-subscription", component: <ManageSubscription /> },
    { path: "/chatbot", component: <Chatbot /> },
    { path: "/image-generator", component: <ImageGenerator /> },
    { path: "/voicegenerator", component: <VoiceGenerator /> },
    { path: "/faq", component: <Faq /> },
];

const nonAuthRoutes: RouteProps[] = [
    { path: "/register", component: <Register /> },
    { path: "/login", component: <Login /> },
    { path: "/reset-password", component: <ResetPassword /> },
]

export {
    routes,
    nonAuthRoutes
};
