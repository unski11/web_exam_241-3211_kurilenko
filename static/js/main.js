document.addEventListener("click", (event) => {
  const openButton = event.target.closest("[data-modal-open]");
  if (openButton) {
    const dialog = document.getElementById(openButton.dataset.modalOpen);
    if (dialog) dialog.showModal();
  }

  if (event.target.closest("[data-modal-close]")) {
    event.target.closest("dialog")?.close();
  }
});
