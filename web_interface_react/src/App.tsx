import React from "react";
import Layout from "./modules/shared/components/Layout/Layout";
import Authorization from "./modules/shared/components/Authorization/authorization";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Link from "./modules/shared/pages/link";
import Webpage from "./modules/shared/pages/webpage";
import Youtube from "./modules/shared/pages/youtube";
import Movie from "./modules/shared/pages/movie";
import Email from "./modules/shared/pages/email";
import Search from "./modules/shared/pages/search";
import List from "./modules/shared/pages/list";
import UploadFile from "./modules/shared/pages/file";
import Connect from "./modules/shared/pages/connect";
import Chunks from "./modules/shared/pages/chunks";
import Read from "./modules/shared/pages/read";
import Persons from "./modules/shared/pages/persons";
import PersonsReview from "./modules/shared/pages/personsReview";
import { AuthorizationContext } from "./modules/shared/context/authorizationContext";

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { apiKey } = React.useContext(AuthorizationContext);
  if (!apiKey) {
    return <Navigate to="/connect" replace />;
  }
  return <>{children}</>;
};

function App() {
  const location = useLocation();
  const hideAuthorizationBar = location.pathname.startsWith("/read/");

  return (
    <Routes>
      <Route path="/connect" element={<Connect />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <div className="App">
                {!hideAuthorizationBar && <Authorization />}
                <Routes>
                  <Route path="/" element={<Navigate to="/list" />} />
                  <Route path="/webpage/:id?" element={<Webpage />} />
                  <Route path="/link/:id?" element={<Link />} />
                  <Route path="/movie/:id?" element={<Movie />} />
                  <Route path="/youtube/:id?" element={<Youtube />} />
                  <Route path="/email/:id?" element={<Email />} />
                  <Route path="/chunks/:id" element={<Chunks />} />
                  <Route path="/read/:id" element={<Read />} />
                  <Route path="/list" element={<List />} />
                  <Route path="/persons/:id?" element={<Persons />} />
                  <Route path="/persons-review" element={<PersonsReview />} />
                  <Route path="/search" element={<Search />} />
                  <Route path="/upload-file" element={<UploadFile />} />
                  <Route path="*" element={<p>404</p>} />
                </Routes>
              </div>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default App;
