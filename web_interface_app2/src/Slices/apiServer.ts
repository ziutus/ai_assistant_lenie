import { createSlice, PayloadAction } from "@reduxjs/toolkit";

// Interfejs dla stanu
export interface ApiState {
    apiServer: string;
    apiKey: string;
}

// Stan początkowy
const initialState: ApiState = {
    apiServer: import.meta.env.VITE_API_SERVER || "",
    apiKey: ""
};

// Tworzenie slice przy użyciu createSlice z Redux Toolkit
const apiSlice = createSlice({
    name: 'api',
    initialState,
    reducers: {
        updateApiServer(state: ApiState, action: PayloadAction<string>) {
            state.apiServer = action.payload;
        },
        updateApiKey(state: ApiState, action: PayloadAction<string>) {
            state.apiKey = action.payload;
        }
    }
});

// Eksport akcji i reducera
export const { updateApiServer, updateApiKey } = apiSlice.actions;
export default apiSlice.reducer;
