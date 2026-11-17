const confirmarWhatsApp = document.querySelector("#confirmar-whatsapp[data-codigo]");

if (confirmarWhatsApp) {
  const chave = "pedido-whatsapp:" + confirmarWhatsApp.dataset.codigo;
  try {
    if (!sessionStorage.getItem(chave)) {
      sessionStorage.setItem(chave, "1");
      location.assign(confirmarWhatsApp.href);
    }
  } catch {
    // O link manual segue ativo se o armazenamento estiver restrito.
  }
}
