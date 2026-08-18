import React from "react";
import classes from "./layout.module.css";
import { lenie_version } from "../../constants/variables";
import { NavLink } from "react-router-dom";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";

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
          to="/service-status"
          className={({ isActive }) => isActive ? classes.activeLink : classes.link}
        >
          Status usług
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
        <NavLink to="/chapter-groups" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Kategorie fragmentów</NavLink>
        <NavLink to="/feed-review" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Kuracja feedów</NavLink>
        <NavLink to="/tool-candidates-review" className={({ isActive }) => isActive ? classes.activeLink : classes.link}>Kandydaci-narzędzia</NavLink>
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

type CloudFerroStatus = { status: "warning" | "down"; failures: number; last_error_code: string | null };

const DependencyWarning = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [alert, setAlert] = React.useState<CloudFerroStatus | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const response = await axios.get(`${apiUrl}/service_status`, { headers: { "x-api-key": apiKey ?? "" } });
        const cloudferro = response.data.services?.find((service: any) => service.id === "cloudferro" || service.id === "cloudferro_llm");
        if (!cancelled) setAlert(cloudferro && ["warning", "down"].includes(cloudferro.status) ? cloudferro : null);
      } catch { /* The page itself stays usable while status is unavailable. */ }
    };
    void check();
    const timer = window.setInterval(() => void check(), 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [apiKey, apiUrl]);
  if (!alert) return null;
  const unavailable = alert.status === "down";
  return <div style={{ marginBottom: 12, padding: "10px 12px", borderRadius: 6, border: `1px solid ${unavailable ? "#fca5a5" : "#fcd34d"}`, background: unavailable ? "#fef2f2" : "#fffbeb", color: unavailable ? "#991b1b" : "#92400e" }}>
    <strong>{unavailable ? "CloudFerro nie odpowiada" : "CloudFerro zgłasza błędy"}.</strong>{" "}
    Automatyczne etapy LLM i embeddingów mogą czekać na timeout; backend pozostaje dostępny.
    {alert.last_error_code ? ` Ostatni błąd: ${alert.last_error_code}.` : ""} {alert.failures} błędów w ostatnim oknie. {" "}
    <NavLink to="/service-status" style={{ color: "inherit", fontWeight: 700 }}>Zobacz status usług</NavLink>
  </div>;
};

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
            <div className={classes.content}><DependencyWarning />{children}</div>
        </main>
    );
};
(Layout as any).SideNavigation = SideNavigation;

export default Layout;
