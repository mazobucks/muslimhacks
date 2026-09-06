const dialog = document.getElementById('add_elder_dialog');
const openAddElder = document.getElementById('openAddElder');
const closeAddElder = document.getElementById('closeAddElder');

// Open the dialog as a modal window
openAddElder.addEventListener('click', () => {
  dialog.showModal(); 
});

// Close the dialog
closeAddElder.addEventListener('click', () => {
  dialog.close();
});