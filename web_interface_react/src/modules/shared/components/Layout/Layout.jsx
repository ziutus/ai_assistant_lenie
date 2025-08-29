import React from "react";
import classes from "./layout.module.css";
import { lenie_version } from "../../constants/variables";
import { NavLink } from "react-router-dom";

const SideNavigation = ({ isMenuOpen, toggleMenu }) => {
  const [addOpened, setAddOpened] = React.useState(true);
  return (
    <aside className={`${classes.sideNavigation} ${isMenuOpen ? classes.menuOpen : classes.menuClosed}`}>
      <div className={classes.logo}>
        <h1>Lenie</h1>
        <span>v{lenie_version}</span>
      </div>
      <div className={classes.linksContent}>
        <NavLink to="/list" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>
          Links List
        </NavLink>
        <button className={classes.link} onClick={() => setAddOpened(!addOpened)}>Type </button>

        {!!addOpened ? (
          <div className={classes.subLinkBox}>
            <NavLink
              to="/link"
              className={({ isActive }) =>
                isActive
                  ? `${classes.subLink} ${classes.activeLink}`
                  : `${classes.subLink} ${classes.link}`
              }
            >
              Link
            </NavLink>
            <NavLink
              to="/webpage" className={({ isActive }) =>
                isActive
                  ? `${classes.subLink} ${classes.activeLink}`
                  : `${classes.subLink} ${classes.link}`
              }
            > Webpage (Alfa)
            </NavLink>
            <NavLink
              to="/movie"
              className={({ isActive }) =>
                isActive
                  ? `${classes.subLink} ${classes.activeLink}`
                  : `${classes.subLink} ${classes.link}`
              }
            >
              Movie (Alfa)
            </NavLink>
            <NavLink
              to="/youtube"
              className={({ isActive }) =>
                isActive
                  ? `${classes.subLink} ${classes.activeLink}`
                  : `${classes.subLink} ${classes.link}`
              }
            >
              Youtube (Alfa)
            </NavLink>
          </div>
        ) : null}
        <NavLink
          to="/search"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Search
        </NavLink>
        <NavLink
          to="/upload-file"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Upload File (Alfa)
        </NavLink>
      </div>
    </aside>
  );
};

const Layout = ({ children }) => {
    const [isMenuOpen, setIsMenuOpen] = React.useState(false);
    const toggleMenu = () => setIsMenuOpen(!isMenuOpen);

    return (
        <main>
            <button className={classes.hamburger} onClick={toggleMenu}>
                &#9776;
            </button>
            <SideNavigation isMenuOpen={isMenuOpen} toggleMenu={toggleMenu} />
            <div className={classes.content}>{children}</div>
        </main>
    );
};
Layout.SideNavigation = SideNavigation;

export default Layout;
