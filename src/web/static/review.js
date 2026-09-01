const card = document.getElementById("card");
const token = card.dataset.token;
let products = [];
let index = 0;
let pointerStartX = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderChips(containerId, values, selected, onSelect) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  values.forEach((v) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (String(v) === String(selected) ? " active" : "");
    btn.textContent = v;
    btn.onclick = () => onSelect(v);
    el.appendChild(btn);
  });
}

function currentProduct() {
  return products[index];
}

async function saveFields() {
  const p = currentProduct();
  const body = {
    name: document.getElementById("name").value,
    price: Number(document.getElementById("price-custom").value || p.price),
    discount_percent: Number(document.getElementById("discount-custom").value || p.discount_percent),
    quantity: Number(document.getElementById("quantity-custom").value || p.quantity),
  };
  await api(`/api/review/${token}/products/${p.id}`, { method: "PATCH", body: JSON.stringify(body) });
  Object.assign(p, body);
}

function showProduct() {
  const p = currentProduct();
  if (!p) return;
  document.getElementById("progress").textContent = `Product ${index + 1} of ${products.length}`;
  document.getElementById("original-image").src = p.original_image_url;
  document.getElementById("generated-image").src = p.generated_image_url;
  if (p.generation_failed) {
    document.getElementById("generated-image").alt = "Generation failed — showing original";
  }
  document.getElementById("name").value = p.name;
  document.getElementById("price-custom").value = p.price;
  document.getElementById("discount-custom").value = p.discount_percent;
  document.getElementById("quantity-custom").value = p.quantity;
  renderChips("price-chips", p.options.price, p.price, (v) => {
    p.price = v;
    document.getElementById("price-custom").value = v;
    saveFields();
    showProduct();
  });
  renderChips("discount-chips", p.options.discount, p.discount_percent, (v) => {
    p.discount_percent = v;
    document.getElementById("discount-custom").value = v;
    saveFields();
    showProduct();
  });
  renderChips("quantity-chips", p.options.quantity, p.quantity, (v) => {
    p.quantity = v;
    document.getElementById("quantity-custom").value = v;
    saveFields();
    showProduct();
  });
}

async function swipe(direction, dx = 0, dy = 0) {
  await saveFields();
  const p = currentProduct();
  const result = await api(`/api/review/${token}/products/${p.id}/swipe`, {
    method: "POST",
    body: JSON.stringify({ direction, dx, dy }),
  });
  p.decision = result.decision;
  if (index < products.length - 1) {
    index += 1;
    showProduct();
  } else {
    document.getElementById("status").textContent = "Last product reviewed.";
  }
}

document.getElementById("approve").onclick = () => swipe("right");
document.getElementById("reject").onclick = () => swipe("left");
document.getElementById("prev").onclick = () => {
  if (index > 0) {
    index -= 1;
    showProduct();
  }
};
document.getElementById("next").onclick = async () => {
  await saveFields();
  if (index < products.length - 1) {
    index += 1;
    showProduct();
  }
};
document.getElementById("finish").onclick = async () => {
  await saveFields();
  const result = await api(`/api/review/${token}/finish`, { method: "POST" });
  document.getElementById("status").textContent =
    `Done. Approved: ${result.approved}, rejected: ${result.rejected}, Shopify ok: ${result.shopify_ok}, skipped: ${result.shopify_skipped}`;
};

const wrap = document.getElementById("image-wrap");
wrap.addEventListener("pointerdown", (e) => {
  pointerStartX = e.clientX;
});
wrap.addEventListener("pointerup", (e) => {
  if (pointerStartX === null) return;
  const dx = e.clientX - pointerStartX;
  pointerStartX = null;
  if (Math.abs(dx) > 60) {
    swipe(dx > 0 ? "right" : "left", dx, 0);
  }
});

api(`/api/review/${token}`)
  .then((data) => {
    products = data.products;
    if (data.expires_at) {
      const expires = new Date(data.expires_at);
      document.getElementById("expiry").textContent =
        `Link expires ${expires.toLocaleString()}`;
    }
    showProduct();
  })
  .catch((err) => {
    document.getElementById("status").textContent = "Failed to load review session.";
    console.error(err);
  });
