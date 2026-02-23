//import images
import icons01 from "assets/images/icons/01.png";
import icons02 from "assets/images/icons/02.png";
import icons03 from "assets/images/icons/03.png";
import icons04 from "assets/images/icons/04.png";
import icons05 from "assets/images/icons/05.png";
import icons06 from "assets/images/icons/06.png";
import icons07 from "assets/images/icons/07.png";
import icons08 from "assets/images/icons/08.png";
import icons09 from "assets/images/icons/09.png";

const menuData = [
    {
        title: "Home",
        link: "/",
        icon: icons01,
        subMenu: [],
    },
    {
        title: "Community Feed",
        link: "/community-feed",
        icon: icons02,
        subMenu: [],
    },
    {
        title: "Community Details",
        link: "/community-details",
        icon: icons02,
        subMenu: [],
    },
    {
        title: "Manage Subscription",
        link: "/manage-subscription",
        icon: icons03,
        subMenu: [],
    },
    {
        title: "AI Chat Bot",
        link: "/chatbot",
        icon: icons04,
        subMenu: [],
    },
    {
        title: "Image Generator",
        link: "/image-generator",
        icon: icons05,
        subMenu: [],
    },
    {
        title: "Voice Generate",
        link: "/voicegenerator",
        icon: icons06,
        subMenu: [],
    },
    {
        title: "Register",
        link: "/register",
        icon: icons07,
        subMenu: [],
    },
    {
        title: "Settings",
        link: "#",
        icon: icons08,
        subMenu: [
            { title: "FAQ's", link: "/faq" },
            { title: "Log In", link: "/login" },
            { title: "Reset Password", link: "/reset-password" },
            { title: "Community Details", link: "/community-details" },
        ],
    },
    {
        title: "Logout",
        link: "#",
        icon: icons09,
        subMenu: [],
    },
];

export {
    menuData
};
