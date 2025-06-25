import React, { useState, useRef, useEffect } from 'react';
import { Settings, Sun, Moon, Monitor, ChevronRight, Lock, LogOut, User } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import ChangePasswordModal from './ChangePasswordModal';

const SettingsDropdown = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ left: 0, top: 0 });
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (isOpen && dropdownRef.current) {
      const rect = dropdownRef.current.getBoundingClientRect();
      const dropdownHeight = 240; // estimated height of dropdown
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;
      
      // Start with aligning to the top of the button
      let top = rect.top;
      let left = rect.right + 4;
      
      // Check if dropdown would go off the bottom of the screen
      if (top + dropdownHeight > viewportHeight - 20) {
        // Position above the button instead
        top = rect.bottom - dropdownHeight;
        // If still off-screen, position at bottom with margin
        if (top < 20) {
          top = viewportHeight - dropdownHeight - 20;
        }
      }
      
      // Check if dropdown would go off the right edge
      if (left + 224 > viewportWidth) { // 224px = w-56
        left = rect.left - 224 - 8; // Position to the left of button instead
      }
      
      setDropdownPosition({
        left: Math.max(8, left), // Ensure at least 8px from left edge
        top: Math.max(8, top) // Ensure at least 8px from top
      });
    }
  }, [isOpen]);

  const getThemeIcon = () => {
    switch (theme) {
      case 'dark':
        return <Moon className="h-4 w-4" />;
      case 'light':
        return <Sun className="h-4 w-4" />;
      default:
        return <Monitor className="h-4 w-4" />;
    }
  };

  return (
    <div className="relative" ref={dropdownRef} style={{ overflow: 'visible' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 group text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-white dark:hover:bg-gray-800 hover:shadow-sm"
      >
        <Settings className="h-5 w-5 mr-3 transition-transform duration-200 group-hover:scale-105" />
        <span className="flex-1 text-left">Settings</span>
        <ChevronRight className={`h-3 w-3 transition-transform duration-200 ${isOpen ? 'rotate-0' : 'rotate-0'}`} />
      </button>

      {isOpen && (
        <div 
          className="fixed w-56 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 animate-slideDown" 
          style={{ 
            left: `${dropdownPosition.left}px`,
            top: `${dropdownPosition.top}px`,
            maxHeight: '380px',
            zIndex: 9999
          }}>
          <div className="py-1 overflow-y-auto max-h-full">
            {/* Theme Section */}
            <div className="px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
              Appearance
            </div>
            
            <button
              onClick={() => {
                toggleTheme();
                setIsOpen(false);
              }}
              className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <div className="flex items-center space-x-3">
                {getThemeIcon()}
                <span>Theme</span>
              </div>
              <span className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                {theme}
              </span>
            </button>

            {/* User Account Section */}
            <div className="border-t border-gray-200 dark:border-gray-700 mt-1 pt-1">
              <div className="px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Account
              </div>
              
              <div className="px-3 py-2 flex items-center space-x-3">
                <User className="h-4 w-4 text-gray-400" />
                <div className="flex-1">
                  <div className="text-sm text-gray-700 dark:text-gray-300">{user?.username}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Administrator</div>
                </div>
              </div>
              
              <button
                onClick={() => {
                  setShowChangePassword(true);
                  setIsOpen(false);
                }}
                className="w-full flex items-center space-x-3 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <Lock className="h-4 w-4" />
                <span>Change Password</span>
              </button>
              
              <button
                onClick={() => {
                  logout();
                  setIsOpen(false);
                }}
                className="w-full flex items-center space-x-3 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      )}
      
      <ChangePasswordModal 
        isOpen={showChangePassword} 
        onClose={() => setShowChangePassword(false)} 
      />
    </div>
  );
};

export default SettingsDropdown; 