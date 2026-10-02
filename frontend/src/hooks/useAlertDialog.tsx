import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Button } from '../components/ui/button';

interface AlertDialogConfig {
  title?: string;
  message: string;
  variant?: 'default' | 'success' | 'error' | 'warning';
}

interface AlertDialogContextType {
  showAlert: (config: AlertDialogConfig) => void;
}

const AlertDialogContext = createContext<AlertDialogContextType | undefined>(undefined);

export const AlertDialogProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<AlertDialogConfig>({ message: '' });

  const showAlert = useCallback((newConfig: AlertDialogConfig) => {
    setConfig(newConfig);
    setIsOpen(true);
  }, []);

  const handleClose = () => {
    setIsOpen(false);
  };

  const getTitle = () => {
    if (config.title) return config.title;

    switch (config.variant) {
      case 'success':
        return 'Success';
      case 'error':
        return 'Error';
      case 'warning':
        return 'Warning';
      default:
        return 'Information';
    }
  };

  return (
    <AlertDialogContext.Provider value={{ showAlert }}>
      {children}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{getTitle()}</DialogTitle>
            <DialogDescription className="whitespace-pre-wrap">
              {config.message}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={handleClose}>OK</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AlertDialogContext.Provider>
  );
};

export const useAlertDialog = () => {
  const context = useContext(AlertDialogContext);
  if (!context) {
    throw new Error('useAlertDialog must be used within an AlertDialogProvider');
  }
  return context;
};
