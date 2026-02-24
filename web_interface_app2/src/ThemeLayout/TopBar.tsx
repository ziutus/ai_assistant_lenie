import React, { useContext, useEffect, useState } from "react";
import { Col } from "react-bootstrap";
import { Link } from "react-router-dom";
import ManageSubscription from "Common/ManageSubscription";
import { useDispatch, useSelector } from "react-redux";
import { THEME_MODE, THEME_SIDEBAR_TOGGLE, changeTheme, changeSidebarThemeToggle } from "Slices/theme/reducer";
import { RootState } from "Slices/theme/store";
import { AuthContext } from "../context/AuthContext";

//images
import logo01 from "assets/images/logo/logo-lenie-ai.png";
import icons01 from "assets/images/icons/01.svg";
import icons02 from "assets/images/icons/02.svg";
import user1 from "assets/images/avatar/user.svg";
import avatar_user from "assets/images/users/jozwiak_krzysztof_logged_in.jpeg";



const TopBar = () => {
    const { logout } = useContext(AuthContext);
    const [isUpdateSubscription, setIsUpdateSubscription] = useState<boolean>(false);

    const toggleUpdateSubscription = () => {
        setIsUpdateSubscription(!isUpdateSubscription);
    };

    const [isSearch, setIsSearch] = useState(false);

    const toggleSearch = () => {
        setIsSearch(!isSearch);
    };

    const [isNotification, setIsNotification] = useState(false);

    const toggleNotification = () => {
        setIsNotification(!isNotification);
    };

    const [isLanguage, setIsLanguage] = useState(false);

    const toggleLanguage = () => {
        setIsLanguage(!isLanguage);
    };

    const [isProfile, setIsProfile] = useState(false);

    const toggleProfile = () => {
        setIsProfile(!isProfile);
    };

    const themeType = useSelector((state: RootState) => state.theme.themeType);
    const dispatch = useDispatch();

    const toggleModeTheme = () => {
        const newTheme = themeType === THEME_MODE.LIGHT ? THEME_MODE.DARK : THEME_MODE.LIGHT;
        document.documentElement.setAttribute("data-theme", newTheme);
        dispatch(changeTheme(newTheme));
    };

    useEffect(() => {
        document.documentElement.setAttribute("data-theme", themeType);
    }, [themeType]);

    //Toggle sidebar
    const themeSidebarToggle = useSelector((state: RootState) => state.theme.themeSidebarToggle);
    const [isSidebarToggle, setIsSidebarToggle] = useState<boolean>(false);
    const user = useSelector((state: RootState) => state.user);

    // Update isSidebarToggle based on themeSidebarToggle when it changes
    useEffect(() => {
        setIsSidebarToggle(themeSidebarToggle === THEME_SIDEBAR_TOGGLE.TRUE);
    }, [themeSidebarToggle]);

    const toggleSidebar = () => {
        const newToggleValue = !isSidebarToggle;
        setIsSidebarToggle(newToggleValue);
        // Dispatch action based on the new toggle value
        dispatch(changeSidebarThemeToggle(newToggleValue ? THEME_SIDEBAR_TOGGLE.TRUE : THEME_SIDEBAR_TOGGLE.FALSE));
    };
    return (
        <>
            <div className="header-area-one">
                <div className="container-30">
                    <Col lg={12}>
                        <div className="header-inner-one">
                            <div className="left-logo-area">
                                <Link to="/" className="logo">
                                    <img src={logo01} alt="logo-image" />
                                </Link>
                                <div onClick={toggleSidebar} className={`left-side-open-clouse ${themeSidebarToggle ? "collapsed" : ""}`} id="collups-left">
                                    <img src={icons01} alt="icons" />
                                </div>
                            </div>
                            <div className="header-right">
                                <div className="button-area">
                                    <Link
                                        onClick={toggleUpdateSubscription}
                                        to="#"
                                        className="rts-btn btn-primary"
                                    >
                                        <img src={icons02} alt="icons" />
                                        Update
                                    </Link>
                                </div>
                                <div className="action-interactive-area__header">
                                    <div className="single_action__haeader search-action openuptip" >
                                        <svg onClick={toggleSearch} width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M18.1247 17.2413L13.4046 12.5213C14.5388 11.1596 15.1044 9.41313 14.9837 7.6451C14.863 5.87707 14.0653 4.22363 12.7566 3.02875C11.4479 1.83388 9.72885 1.18955 7.95716 1.22981C6.18548 1.27007 4.49752 1.99182 3.24442 3.24491C1.99133 4.498 1.26958 6.18597 1.22932 7.95765C1.18906 9.72934 1.83339 11.4483 3.02827 12.7571C4.22315 14.0658 5.87658 14.8635 7.64461 14.9842C9.41264 15.1049 11.1591 14.5393 12.5208 13.4051L17.2408 18.1251L18.1247 17.2413ZM2.49966 8.12515C2.49966 7.01263 2.82956 5.92509 3.44764 5.00006C4.06573 4.07504 4.94423 3.35407 5.97206 2.92833C6.9999 2.50258 8.1309 2.39119 9.22204 2.60823C10.3132 2.82527 11.3155 3.361 12.1021 4.14767C12.8888 4.93434 13.4245 5.93662 13.6416 7.02776C13.8586 8.11891 13.7472 9.24991 13.3215 10.2777C12.8957 11.3056 12.1748 12.1841 11.2497 12.8022C10.3247 13.4202 9.23718 13.7501 8.12466 13.7501C6.63332 13.7485 5.20354 13.1553 4.14901 12.1008C3.09448 11.0463 2.50131 9.61648 2.49966 8.12515Z" fill="#525252" />
                                            <path d="M18.1247 17.2413L13.4046 12.5213C14.5388 11.1596 15.1044 9.41313 14.9837 7.6451C14.863 5.87707 14.0653 4.22363 12.7566 3.02875C11.4479 1.83388 9.72885 1.18955 7.95716 1.22981C6.18548 1.27007 4.49752 1.99182 3.24442 3.24491C1.99133 4.498 1.26958 6.18597 1.22932 7.95765C1.18906 9.72934 1.83339 11.4483 3.02827 12.7571C4.22315 14.0658 5.87658 14.8635 7.64461 14.9842C9.41264 15.1049 11.1591 14.5393 12.5208 13.4051L17.2408 18.1251L18.1247 17.2413ZM2.49966 8.12515C2.49966 7.01263 2.82956 5.92509 3.44764 5.00006C4.06573 4.07504 4.94423 3.35407 5.97206 2.92833C6.9999 2.50258 8.1309 2.39119 9.22204 2.60823C10.3132 2.82527 11.3155 3.361 12.1021 4.14767C12.8888 4.93434 13.4245 5.93662 13.6416 7.02776C13.8586 8.11891 13.7472 9.24991 13.3215 10.2777C12.8957 11.3056 12.1748 12.1841 11.2497 12.8022C10.3247 13.4202 9.23718 13.7501 8.12466 13.7501C6.63332 13.7485 5.20354 13.1553 4.14901 12.1008C3.09448 11.0463 2.50131 9.61648 2.49966 8.12515Z" fill="#083A5E" />
                                        </svg>
                                        <div className="search-opoup slide-down__click" style={{ display: isSearch ? "block" : "none" }}>
                                            <input type="text" placeholder="Search" />
                                            <i className="fa-solid fa-magnifying-glass"></i>
                                        </div>
                                    </div>
                                    <div className="single_action__haeader notification openuptip">
                                        <svg onClick={toggleNotification} width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path fillRule="evenodd" clipRule="evenodd" d="M16.25 8.75V10.3662L17.9419 12.0581C18.0591 12.1753 18.125 12.3343 18.125 12.5V14.375C18.125 14.5408 18.0592 14.6997 17.9419 14.8169C17.8247 14.9342 17.6658 15 17.5 15H13.125V15.625C13.125 16.4538 12.7958 17.2487 12.2097 17.8347C11.6237 18.4208 10.8288 18.75 10 18.75C9.1712 18.75 8.37634 18.4208 7.79029 17.8347C7.20424 17.2487 6.875 16.4538 6.875 15.625V15H2.5C2.33424 15 2.17527 14.9342 2.05806 14.8169C1.94085 14.6997 1.875 14.5408 1.875 14.375V12.5C1.87504 12.3343 1.94091 12.1753 2.05812 12.0581L3.75 10.3662V8.125C3.75201 6.57622 4.32822 5.08319 5.36721 3.93462C6.4062 2.78605 7.83417 2.06352 9.375 1.90675V0.625H10.625V1.90675C11.2723 1.97291 11.9051 2.14078 12.5 2.40419V3.80156C11.7409 3.36005 10.8786 3.12667 10.0005 3.12498C9.12225 3.1233 8.25916 3.35337 7.49832 3.79196C6.73749 4.23055 6.10585 4.86213 5.66719 5.62293C5.22853 6.38373 4.99839 7.2468 5 8.125V10.625C4.99996 10.7907 4.93409 10.9497 4.81687 11.0669L3.125 12.7588V13.75H16.875V12.7588L15.1831 11.0669C15.0659 10.9497 15 10.7907 15 10.625V8.75H16.25ZM11.3258 16.9508C11.6775 16.5992 11.875 16.1223 11.875 15.625V15H8.125V15.625C8.125 16.1223 8.32254 16.5992 8.67417 16.9508C9.02581 17.3025 9.50272 17.5 10 17.5C10.4973 17.5 10.9742 17.3025 11.3258 16.9508ZM18.75 5C18.75 6.38071 17.6307 7.5 16.25 7.5C14.8693 7.5 13.75 6.38071 13.75 5C13.75 3.61929 14.8693 2.5 16.25 2.5C17.6307 2.5 18.75 3.61929 18.75 5Z" fill="#083A5E" />
                                            <path fillRule="evenodd" clipRule="evenodd" d="M16.25 8.75V10.3662L17.9419 12.0581C18.0591 12.1753 18.125 12.3343 18.125 12.5V14.375C18.125 14.5408 18.0592 14.6997 17.9419 14.8169C17.8247 14.9342 17.6658 15 17.5 15H13.125V15.625C13.125 16.4538 12.7958 17.2487 12.2097 17.8347C11.6237 18.4208 10.8288 18.75 10 18.75C9.1712 18.75 8.37634 18.4208 7.79029 17.8347C7.20424 17.2487 6.875 16.4538 6.875 15.625V15H2.5C2.33424 15 2.17527 14.9342 2.05806 14.8169C1.94085 14.6997 1.875 14.5408 1.875 14.375V12.5C1.87504 12.3343 1.94091 12.1753 2.05812 12.0581L3.75 10.3662V8.125C3.75201 6.57622 4.32822 5.08319 5.36721 3.93462C6.4062 2.78605 7.83417 2.06352 9.375 1.90675V0.625H10.625V1.90675C11.2723 1.97291 11.9051 2.14078 12.5 2.40419V3.80156C11.7409 3.36005 10.8786 3.12667 10.0005 3.12498C9.12225 3.1233 8.25916 3.35337 7.49832 3.79196C6.73749 4.23055 6.10585 4.86213 5.66719 5.62293C5.22853 6.38373 4.99839 7.2468 5 8.125V10.625C4.99996 10.7907 4.93409 10.9497 4.81687 11.0669L3.125 12.7588V13.75H16.875V12.7588L15.1831 11.0669C15.0659 10.9497 15 10.7907 15 10.625V8.75H16.25ZM11.3258 16.9508C11.6775 16.5992 11.875 16.1223 11.875 15.625V15H8.125V15.625C8.125 16.1223 8.32254 16.5992 8.67417 16.9508C9.02581 17.3025 9.50272 17.5 10 17.5C10.4973 17.5 10.9742 17.3025 11.3258 16.9508ZM18.75 5C18.75 6.38071 17.6307 7.5 16.25 7.5C14.8693 7.5 13.75 6.38071 13.75 5C13.75 3.61929 14.8693 2.5 16.25 2.5C17.6307 2.5 18.75 3.61929 18.75 5Z" fill="#083A5E" />
                                        </svg>

                                        <div className="notification_main_wrapper slide-down__click" style={{ display: isNotification ? "block" : "none" }}>
                                            <h3 className="title">
                                                Notification<span className="count">5</span>
                                            </h3>
                                            <div className="notification__content">
                                                <ul className="notification__items">
                                                    <li className="single__items">
                                                        <Link className="single-link" to="#">
                                                            <div className="avatar">
                                                                <img src={user1} alt="Popup Img" className="" />
                                                            </div>
                                                            <div className="main-content">
                                                                <h5 className="name-user">
                                                                    MR.Crow Kader
                                                                    <span className="time-ago">1.3 hrs ago</span>
                                                                </h5>
                                                                <div className="disc">
                                                                    Lorem ipsum dolor amet cosec...
                                                                    <span className="count"></span>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    </li>
                                                    <li className="single__items">
                                                        <Link className="single-link" to="#">
                                                            <div className="avatar">
                                                                <img src={user1} alt="Popup Img" className="" />
                                                            </div>
                                                            <div className="main-content">
                                                                <h5 className="name-user">
                                                                    MR.Crow Kader
                                                                    <span className="time-ago">1.3 hrs ago</span>
                                                                </h5>
                                                                <div className="disc">
                                                                    Lorem ipsum dolor amet cosec...
                                                                    <span className="count"></span>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    </li>
                                                    <li className="single__items">
                                                        <Link className="single-link" to="#">
                                                            <div className="avatar">
                                                                <img src={user1} alt="Popup Img" className="" />
                                                            </div>
                                                            <div className="main-content">
                                                                <h5 className="name-user">
                                                                    MR.Crow Kader
                                                                    <span className="time-ago">1.3 hrs ago</span>
                                                                </h5>
                                                                <div className="disc">
                                                                    Lorem ipsum dolor amet cosec...
                                                                    <span className="count"></span>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    </li>
                                                    <li className="single__items">
                                                        <Link className="single-link" to="#">
                                                            <div className="avatar">
                                                                <img src={user1} alt="Popup Img" className="" />
                                                            </div>
                                                            <div className="main-content">
                                                                <h5 className="name-user">
                                                                    MR.Crow Kader
                                                                    <span className="time-ago">1.3 hrs ago</span>
                                                                </h5>
                                                                <div className="disc">
                                                                    Lorem ipsum dolor amet cosec...
                                                                    <span className="count"></span>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    </li>
                                                    <li className="single__items">
                                                        <Link className="single-link" to="#">
                                                            <div className="avatar">
                                                                <img src={user1} alt="Popup Img" className="" />
                                                            </div>
                                                            <div className="main-content">
                                                                <h5 className="name-user">
                                                                    MR.Crow Kader
                                                                    <span className="time-ago">1.3 hrs ago</span>
                                                                </h5>
                                                                <div className="disc">
                                                                    Lorem ipsum dolor amet cosec...
                                                                    <span className="count"></span>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    </li>
                                                </ul>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="single_action__haeader language  user_avatar__information openuptip">
                                        <svg onClick={toggleLanguage} width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path fillRule="evenodd" clipRule="evenodd" d="M11.25 3.125V4.375H9.25C8.83816 6.14196 7.99661 7.77997 6.8 9.14375C7.70414 10.0661 8.79525 10.7843 10 11.25L9.55625 12.4C8.20367 11.8567 6.97802 11.0396 5.95625 10C4.9156 11.0255 3.68974 11.8442 2.34375 12.4125L1.875 11.25C3.07285 10.7429 4.16632 10.0182 5.1 9.1125C4.2552 8.08229 3.61842 6.89788 3.225 5.625H4.5375C4.85587 6.57383 5.3405 7.45844 5.96875 8.2375C6.93251 7.12787 7.6162 5.80335 7.9625 4.375H1.25V3.125H5.625V1.25H6.875V3.125H11.25ZM18.75 18.125H17.4062L16.4062 15.625H12.125L11.125 18.125H9.78125L13.5312 8.75H15L18.75 18.125ZM14.2625 10.275L12.625 14.375H15.9062L14.2625 10.275Z" fill="black" />
                                            <path fillRule="evenodd" clipRule="evenodd" d="M11.25 3.125V4.375H9.25C8.83816 6.14196 7.99661 7.77997 6.8 9.14375C7.70414 10.0661 8.79525 10.7843 10 11.25L9.55625 12.4C8.20367 11.8567 6.97802 11.0396 5.95625 10C4.9156 11.0255 3.68974 11.8442 2.34375 12.4125L1.875 11.25C3.07285 10.7429 4.16632 10.0182 5.1 9.1125C4.2552 8.08229 3.61842 6.89788 3.225 5.625H4.5375C4.85587 6.57383 5.3405 7.45844 5.96875 8.2375C6.93251 7.12787 7.6162 5.80335 7.9625 4.375H1.25V3.125H5.625V1.25H6.875V3.125H11.25ZM18.75 18.125H17.4062L16.4062 15.625H12.125L11.125 18.125H9.78125L13.5312 8.75H15L18.75 18.125ZM14.2625 10.275L12.625 14.375H15.9062L14.2625 10.275Z" fill="#083A5E" />
                                        </svg>
                                        <div className="user_information_main_wrapper slide-down__click language-area" style={{ display: isLanguage ? "block" : "none" }}>
                                            <ul className="select-language-area">
                                                <li><Link to="#">English</Link></li>
                                                <li><Link to="#">Polish</Link></li>
                                            </ul>
                                        </div>

                                    </div>
                                    <div className="single_action__haeader rts-dark-light openuptip" id="rts-data-toggle">
                                        <div onClick={toggleModeTheme} style={{ cursor: 'pointer' }}>
                                            {themeType === 'light' ? (
                                                <div className="in-light">
                                                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        <path fillRule="evenodd" clipRule="evenodd" d="M10.625 1.25H9.375V4.375H10.625V1.25ZM15.7452 3.37099L13.5541 5.56213L14.4379 6.44593L16.629 4.25478L15.7452 3.37099ZM15.625 9.375H18.75V10.625H15.625V9.375ZM14.4379 13.5541L13.5541 14.4379L15.7452 16.629L16.629 15.7452L14.4379 13.5541ZM9.375 15.625H10.625V18.75H9.375V15.625ZM5.56212 13.5541L3.37097 15.7452L4.25477 16.629L6.44591 14.4379L5.56212 13.5541ZM1.25 9.375H4.375V10.625H1.25V9.375ZM4.25479 3.37097L3.37099 4.25476L5.56214 6.44591L6.44593 5.56211L4.25479 3.37097ZM11.3889 7.92133C10.9778 7.64662 10.4945 7.5 10 7.5C9.33719 7.50074 8.70174 7.76438 8.23306 8.23306C7.76438 8.70174 7.50075 9.33719 7.5 10C7.5 10.4945 7.64662 10.9778 7.92133 11.3889C8.19603 11.8 8.58648 12.1205 9.04329 12.3097C9.50011 12.4989 10.0028 12.5484 10.4877 12.452C10.9727 12.3555 11.4181 12.1174 11.7678 11.7678C12.1174 11.4181 12.3555 10.9727 12.452 10.4877C12.5484 10.0028 12.4989 9.50011 12.3097 9.04329C12.1205 8.58648 11.8 8.19603 11.3889 7.92133ZM7.91661 6.88199C8.5333 6.46993 9.25832 6.25 10 6.25C10.9946 6.25 11.9484 6.64509 12.6517 7.34835C13.3549 8.05161 13.75 9.00544 13.75 10C13.75 10.7417 13.5301 11.4667 13.118 12.0834C12.706 12.7001 12.1203 13.1807 11.4351 13.4645C10.7498 13.7484 9.99584 13.8226 9.26841 13.6779C8.54098 13.5333 7.8728 13.1761 7.34835 12.6517C6.8239 12.1272 6.46675 11.459 6.32206 10.7316C6.17736 10.0042 6.25163 9.25016 6.53545 8.56494C6.81928 7.87971 7.29993 7.29404 7.91661 6.88199Z" fill="#08395D" />
                                                    </svg>
                                                </div>
                                            ) : (
                                                <div className="in-dark">
                                                    <svg width="18" height="16" viewBox="0 0 18 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        <path d="M2.43606 9.58151C3.65752 9.87564 4.92547 9.92252 6.16531 9.71938C7.40516 9.51625 8.59186 9.0672 9.65559 8.39867C10.7193 7.73013 11.6386 6.85561 12.3594 5.82654C13.0802 4.79747 13.5878 3.63465 13.8526 2.40648C14.5174 3.05723 15.0448 3.83492 15.4033 4.69337C15.7619 5.55183 15.9443 6.47357 15.9398 7.40388C15.9393 7.49044 15.9419 7.57777 15.9382 7.665C15.8708 9.2842 15.2384 10.8287 14.1508 12.0301C13.0632 13.2316 11.5892 14.0141 9.98463 14.2419C8.38012 14.4696 6.74651 14.1282 5.36754 13.2768C3.98858 12.4255 2.95137 11.118 2.43606 9.58151V9.58151ZM0.933336 8.6487C0.933165 8.68529 0.9362 8.72182 0.942407 8.75788C1.28351 10.7502 2.34974 12.5458 3.93575 13.7989C5.52175 15.052 7.51534 15.6739 9.53252 15.5449C11.5497 15.4158 13.4478 14.545 14.8612 13.1C16.2746 11.655 17.1033 9.73813 17.1878 7.71859C17.1921 7.61606 17.189 7.51347 17.1897 7.41179C17.1985 6.10006 16.8914 4.80548 16.2943 3.6375C15.6972 2.46953 14.8276 1.4625 13.7591 0.701557C13.667 0.639835 13.5603 0.603476 13.4496 0.59614C13.339 0.588804 13.2284 0.610752 13.129 0.659772C13.0295 0.708793 12.9447 0.783154 12.8832 0.875366C12.8216 0.967579 12.7855 1.07438 12.7783 1.18503C12.661 2.43295 12.2583 3.63719 11.6014 4.70467C10.9444 5.77214 10.0508 6.67425 8.98959 7.34127C7.92838 8.00829 6.728 8.42235 5.48124 8.55146C4.23448 8.68056 2.97473 8.52125 1.79936 8.08583C1.70533 8.04882 1.60382 8.03482 1.50329 8.04497C1.40276 8.05511 1.30522 8.08909 1.21997 8.14437C1.13473 8.19965 1.0642 8.27463 1.01418 8.36272C0.964152 8.45082 0.936972 8.54983 0.933336 8.65037V8.6487Z" fill="#F3F3F3" />
                                                    </svg>
                                                </div>
                                            )}
                                        </div>

                                    </div>
                                    <div className="single_action__haeader user_avatar__information openuptip">
                                        <div onClick={toggleProfile} className="avatar">
                                            <img src={avatar_user} alt="avatar" />
                                        </div>
                                        <div style={{ display: isProfile ? "block" : "none" }} className="user_information_main_wrapper slide-down__click">
                                            <div className="user_header">
                                                <div className="main-avatar">
                                                    <img src={avatar_user} alt="user" />
                                                </div>
                                                <div className="user_naim-information">
                                                    <h3 className="title">{user.name}</h3>
                                                    <span className="desig">{user.description}</span>
                                                </div>
                                            </div>
                                            <div className="user_body_content">
                                                <ul className="items">
                                                    <li className="single_items">
                                                        <Link className="hader_popup_link" to="/profile">
                                                            <i className="fa-light fa-user"></i>
                                                            Profile
                                                        </Link>
                                                    </li>
                                                    <li className="single_items">
                                                        <Link className="hader_popup_link" to="#">
                                                            <i className="fa-regular fa-gear"></i>
                                                            Settings
                                                        </Link>
                                                    </li>
                                                    <li className="single_items">
                                                        <Link className="hader_popup_link" to="#">
                                                            <i className="fa-light fa-person-snowmobiling"></i>
                                                            Billing
                                                        </Link>
                                                    </li>
                                                    <li className="single_items">
                                                        <Link className="hader_popup_link" to="#">
                                                            <i className="fa-solid fa-wave-pulse"></i>
                                                            Activity
                                                        </Link>
                                                    </li>
                                                    <li className="single_items">
                                                        <Link className="hader_popup_link" to="#">
                                                            <i className="fa-regular fa-bell"></i>
                                                            Help
                                                        </Link>
                                                    </li>
                                                </ul>
                                            </div>
                                            <div className="popup-footer-btn">
                                                <a href="#" className="geex-content__header__popup__footer__link" onClick={(e) => { e.preventDefault(); logout(); }}>Logout
                                                    <i className="fa-light fa-arrow-right"></i>
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </Col>
                </div>
            </div>

            <ManageSubscription
                isUpdateSubscription={isUpdateSubscription}
                toggleUpdateSubscription={toggleUpdateSubscription}
            />
        </>
    );
};

export default TopBar;
