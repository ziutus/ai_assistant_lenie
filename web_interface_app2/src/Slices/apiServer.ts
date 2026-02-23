import { createSlice, PayloadAction } from "@reduxjs/toolkit";

// Interfejs dla stanu
export interface ApiState {
    apiServer: string;
    apiKey: string;
}

// Stan początkowy
const initialState: ApiState = {
    apiServer: "https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1",
    apiKey: "2n2OUAH6Bm4JN8cNc5Z8EaTO7U2ztWjw1eqVGLXb"
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
