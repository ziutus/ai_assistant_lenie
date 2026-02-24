import { BrowserRouter, Route, Routes } from "react-router-dom"
import { RouteProps, nonAuthRoutes, routes } from "./routes";
import ThemeLayout from "../ThemeLayout";
import NonLayout from "ThemeLayout/NonLayout";

const Routing = () => {
  return (
    <>
      <BrowserRouter>
        <Routes>
          {(nonAuthRoutes || []).map((item: RouteProps, key: number) => (
            <Route key={key} path={item.path} element={
              <NonLayout>
                {item.component}
              </NonLayout>
            } />
          ))}

          {(routes || []).map((item: RouteProps, key: number) => (
            <Route key={key} path={item.path} element={
              <ThemeLayout>
                {item.component}
              </ThemeLayout>
            } />
          ))}
        </Routes>
      </BrowserRouter>
    </>
  );
};

export default Routing;