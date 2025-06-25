import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

// Cookie utility functions
const getCookie = (name) => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
};

const setCookie = (name, value, days = 365) => {
  const expires = new Date();
  expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
  document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Strict`;
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('light');

  useEffect(() => {
    // Load theme from cookie first, then localStorage (for migration), then system preference
    const savedTheme = getCookie('dashboard-theme') || localStorage.getItem('dashboard-theme');
    if (savedTheme && (savedTheme === 'light' || savedTheme === 'dark')) {
      setTheme(savedTheme);
      // Migrate from localStorage to cookie if needed
      if (localStorage.getItem('dashboard-theme') && !getCookie('dashboard-theme')) {
        setCookie('dashboard-theme', savedTheme);
        localStorage.removeItem('dashboard-theme');
      }
    } else {
      // Check system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const initialTheme = prefersDark ? 'dark' : 'light';
      setTheme(initialTheme);
      setCookie('dashboard-theme', initialTheme);
    }
  }, []);

  useEffect(() => {
    // Apply theme to document and save to cookie
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.classList.add(theme);
    // Small delay to ensure DOM is ready before setting cookie
    setTimeout(() => {
      setCookie('dashboard-theme', theme);
    }, 100);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prevTheme => prevTheme === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}; 