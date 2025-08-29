import React from "react";
import Layout from "./modules/shared/components/Layout/Layout";
import Authorization from "./modules/shared/components/Authorization/authorization";
import { Navigate, Route, Routes } from "react-router-dom";
import Link from "./modules/shared/pages/link";
import Webpage from "./modules/shared/pages/webpage";
import Youtube from "./modules/shared/pages/youtube";
import Movie from "./modules/shared/pages/movie";
import Search from "./modules/shared/pages/search";
import List from "./modules/shared/pages/list";
import UploadFile from "./modules/shared/pages/file";

function App() {
  return (
    <>
      <Layout>
        <div className="App">
          <Authorization />
          <Routes>
            <Route path="/" element={<Navigate to="/list" />} />
            <Route path="/webpage/:id?" element={<Webpage />} />
            <Route path="/link/:id?" element={<Link />} />
            <Route path="/movie/:id?" element={<Movie />} />
            <Route path="/youtube/:id?" element={<Youtube />} />
            <Route path="/list" element={<List />} />
            <Route path="/search" element={<Search />} />
            <Route path="/upload-file" element={<UploadFile />} />
            <Route path="*" element={<p>404</p>} />
          </Routes>
        </div>
      </Layout>
    </>
  );
}

export default App;
