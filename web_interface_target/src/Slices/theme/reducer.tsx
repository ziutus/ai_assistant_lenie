// themeSlice.ts

import { createSlice, PayloadAction } from "@reduxjs/toolkit";

// Define theme mode constants
export enum THEME_MODE {
    LIGHT = "light",
    DARK = "dark"
};

export enum THEME_SIDEBAR_TOGGLE {
    TRUE = 1,
    FALSE = 0
};

// Define state interface
export interface ThemeState {
    themeType: THEME_MODE;
    themeSidebarToggle: THEME_SIDEBAR_TOGGLE
}

// Initial state
const initialState: ThemeState = {
    themeType: THEME_MODE.LIGHT,
    themeSidebarToggle: THEME_SIDEBAR_TOGGLE.FALSE
};

// Create slice using createSlice from Redux Toolkit
const themeSlice = createSlice({
    name: 'theme',
    initialState,
    reducers: {
        // Change theme action
        changeTheme(state: ThemeState, action: PayloadAction<THEME_MODE>) {
            state.themeType = action.payload;
        },
        changeSidebarThemeToggle(state: ThemeState, action: PayloadAction<THEME_SIDEBAR_TOGGLE>) {
            state.themeSidebarToggle = action.payload;
        },
    }
});

// Export actions and reducer
export const { changeTheme, changeSidebarThemeToggle } = themeSlice.actions;
export default themeSlice.reducer;
