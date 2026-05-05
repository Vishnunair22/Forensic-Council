/**
 * Global control for the arbiter synthesis process.
 * Allows components like the Navbar to abort an active synthesis
 * regardless of where they are in the component tree.
 */

export const arbiterControl = {
  abortController: null as AbortController | null,
  
  abort: () => {
    if (arbiterControl.abortController) {
      arbiterControl.abortController.abort();
      arbiterControl.abortController = null;
    }
  }
};
