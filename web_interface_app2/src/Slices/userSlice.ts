import { createSlice, PayloadAction } from "@reduxjs/toolkit";

// Interfejs dla stanu użytkownika
export interface UserState {
    name_nice: string;
    name: string;
    description: string;
    email: string;
    access_package: string;
}

// Stan początkowy
const initialState: UserState = {
    name_nice: "Ziutus",
    name: "Krzysztof Józwiak",
    description: "Owner of Lenie-AI",
    email: "krzysztof@itsnap.eu",
    access_package: "Start",
};

// Tworzenie slice przy użyciu createSlice
const userSlice = createSlice({
    name: "user",
    initialState,
    reducers: {
        updateUser(state: UserState, action: PayloadAction<UserState>) {
            return { ...state, ...action.payload };
        },
    },
});

// Eksport akcji i reducera
export const { updateUser } = userSlice.actions;
export default userSlice.reducer;
