// Main JavaScript file for Oleema Production Management System

// Utility Functions
const Utils = {
  // Format currency
  formatCurrency: (amount, currency = 'Rs.') => {
    return `${currency}${parseFloat(amount).toFixed(2)}`;
  },

  // Format date
  formatDate: (date) => {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  },

  // Format number with commas
  formatNumber: (num) => {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  },

  // Show notification
  showNotification: (message, type = 'info') => {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <div class="notification-content">
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
        <button class="notification-close">&times;</button>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
      notification.remove();
    }, 5000);
    
    // Close button functionality
    notification.querySelector('.notification-close').addEventListener('click', () => {
      notification.remove();
    });
  },

  // Validate form
  validateForm: (form) => {
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(input => {
      if (!input.value.trim()) {
        input.classList.add('error');
        isValid = false;
      } else {
        input.classList.remove('error');
      }
    });
    
    return isValid;
  },

  // Debounce function
  debounce: (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }
};

// Sidebar functionality
const Sidebar = {
  init: () => {
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    const sidebarOverlay = document.querySelector('.sidebar-overlay');
    
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        document.querySelector('.main-content').classList.toggle('sidebar-collapsed');
      });
    }
    
    if (sidebarOverlay) {
      sidebarOverlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('open');
      });
    }
  }
};

// Form handling
const Forms = {
  init: () => {
    // Auto-hide error messages on input
    document.querySelectorAll('.form-input').forEach(input => {
      input.addEventListener('input', () => {
        if (input.classList.contains('error')) {
          input.classList.remove('error');
        }
      });
    });
    
    // Form submission handling
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', (e) => {
        if (!Utils.validateForm(form)) {
          e.preventDefault();
          Utils.showNotification('Please fill in all required fields', 'error');
        }
      });
    });
  }
};

// Table functionality
const Tables = {
  init: () => {
    // Sortable tables
    document.querySelectorAll('.table-sortable th[data-sort]').forEach(header => {
      header.addEventListener('click', () => {
        const table = header.closest('table');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const column = header.dataset.sort;
        const isAscending = header.classList.contains('sort-asc');
        
        // Sort rows
        rows.sort((a, b) => {
          const aValue = a.querySelector(`td[data-${column}]`).dataset[column];
          const bValue = b.querySelector(`td[data-${column}]`).dataset[column];
          
          if (isAscending) {
            return aValue > bValue ? -1 : 1;
          } else {
            return aValue < bValue ? -1 : 1;
          }
        });
        
        // Update table
        rows.forEach(row => tbody.appendChild(row));
        
        // Update header classes
        table.querySelectorAll('th').forEach(th => {
          th.classList.remove('sort-asc', 'sort-desc');
        });
        header.classList.add(isAscending ? 'sort-desc' : 'sort-asc');
      });
    });
  }
};

// Charts functionality
const Charts = {
  init: () => {
    // Initialize charts if Chart.js is available
    if (typeof Chart !== 'undefined') {
      // Production chart
      const productionCtx = document.getElementById('productionChart');
      if (productionCtx) {
        new Chart(productionCtx, {
          type: 'line',
          data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            datasets: [{
              label: 'Production Units',
              data: [1200, 1350, 1100, 1400, 1600, 1800],
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              tension: 0.4
            }]
          },
          options: {
            responsive: true,
            plugins: {
              legend: {
                display: false
              }
            },
            scales: {
              y: {
                beginAtZero: true
              }
            }
          }
        });
      }
    }
  }
};

// Initialize all components when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  Sidebar.init();
  Forms.init();
  Tables.init();
  Charts.init();
  
  // Add loading states to buttons
  document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', function() {
      if (this.type === 'submit' && !this.disabled) {
        this.classList.add('btn-loading');
        this.disabled = true;
        
        // Remove loading state after form submission
        setTimeout(() => {
          this.classList.remove('btn-loading');
          this.disabled = false;
        }, 2000);
      }
    });
  });
});

// Export for use in other modules
window.Oleema = {
  Utils,
  Sidebar,
  Forms,
  Tables,
  Charts
};

