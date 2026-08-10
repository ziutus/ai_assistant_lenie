import React from "react";
import classes from "./layout.module.css";
import { lenie_version } from "../../constants/variables";
import { NavLink } from "react-router-dom";

interface SideNavigationProps {
  isMenuOpen: boolean;
  closeMenuOnMobile: () => void;
}

const MOBILE_BREAKPOINT = 768;

const SideNavigation = ({ isMenuOpen, closeMenuOnMobile }: SideNavigationProps) => {
  const [addOpened, setAddOpened] = React.useState(false);
  return (
    <aside className={`${classes.sideNavigation} ${isMenuOpen ? classes.menuOpen : classes.menuClosed}`}>
      <div className={classes.logo}>
        <h1>Lenie</h1>
        <span>v{lenie_version}</span>
      </div>
      <div className={classes.linksContent} onClick={closeMenuOnMobile}>
        <NavLink to="/list" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>
          Links List
        </NavLink>
        <button
          className={classes.link}
          onClick={(e) => {
            e.stopPropagation();
            setAddOpened(!addOpened);
          }}
        >
          {addOpened ? "▾" : "▸"} Nowy dokument
        </button>

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
            <NavLink
              to="/email"
              className={({ isActive }) =>
                isActive
                  ? `${classes.subLink} ${classes.activeLink}`
                  : `${classes.subLink} ${classes.link}`
              }
            >
              Email (Alfa)
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
          to="/persons"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Persons
        </NavLink>
        <NavLink
          to="/persons-review"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Persons Review
        </NavLink>
        <NavLink
          to="/sources"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Sources
        </NavLink>
        <NavLink
          to="/information-sources"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Information Sources
        </NavLink>
        <NavLink
          to="/llm-costs"
          className={({ isActive }) => isActive ? classes.activeLink : classes.link}
        >
          LLM Costs
        </NavLink>
        <NavLink
          to="/upload-file"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Upload File (Alfa)
        </NavLink>
        <NavLink
          to="/stats"
          className={({ isActive }) =>
            isActive ? classes.activeLink : classes.link
          }
        >
          Statystyki
        </NavLink>
        <NavLink to="/feeds" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Feedy</NavLink>
        <NavLink to="/feed-review" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Kuracja feedów</NavLink>
        <NavLink to="/llm-analysis" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Analizy LLM</NavLink>
        <NavLink to="/jobs" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Joby</NavLink>
        <NavLink to="/scheduler" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Scheduler</NavLink>
        <NavLink
          to="/connect"
          className={classes.link}
          style={{ marginTop: 20, borderTop: "1px solid rgb(179, 179, 179)", paddingTop: 17 }}
        >
          Settings
        </NavLink>
      </div>
    </aside>
  );
};

interface LayoutProps {
  children: React.ReactNode;
}

const Layout = ({ children }: LayoutProps) => {
    const [isMenuOpen, setIsMenuOpen] = React.useState(false);
    const toggleMenu = () => setIsMenuOpen(!isMenuOpen);
    const closeMenuOnMobile = () => {
        if (window.innerWidth <= MOBILE_BREAKPOINT) {
            setIsMenuOpen(false);
        }
    };

    return (
        <main>
            <button className={classes.hamburger} onClick={toggleMenu}>
                &#9776;
            </button>
            <SideNavigation isMenuOpen={isMenuOpen} closeMenuOnMobile={closeMenuOnMobile} />
            <div
                className={`${classes.scrim} ${isMenuOpen ? classes.scrimOpen : ""}`}
                onClick={() => setIsMenuOpen(false)}
            />
            <div className={classes.content}>{children}</div>
        </main>
    );
};
(Layout as any).SideNavigation = SideNavigation;

export default Layout;
