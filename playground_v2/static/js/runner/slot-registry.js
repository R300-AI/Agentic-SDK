export const slots = new Map();


export function registerSlot(name, element) {
  slots.set(name, element);
}