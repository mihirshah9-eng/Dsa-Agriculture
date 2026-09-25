# Indexed Max-Heap for Plot Water Stress Scores
class PlotNode:
    """Represents a farm plot entity within the priority queue."""
    def __init__(self, plot_id, water_stress_score, soil_moisture, temperature, humidity):
        self.plot_id = plot_id
        self.water_stress_score = water_stress_score  # Priority Key
        self.soil_moisture = soil_moisture
        self.temperature = temperature
        self.humidity = humidity

    def to_dict(self):
        return {
            "plot_id": self.plot_id,
            "water_stress_score": round(self.water_stress_score, 4),
            "soil_moisture": round(self.soil_moisture, 2),
            "temperature": round(self.temperature, 2),
            "humidity": round(self.humidity, 2)
        }


class IndexedMaxHeap:
    """
    Indexed Max-Binary Heap providing O(1) peek, O(log N) insert, 
    and O(log N) key update via a hash map lookup.
    """
    def __init__(self):
        self.heap = []
        self.position_map = {}  # Hash map: plot_id -> index in self.heap

    def __len__(self):
        return len(self.heap)

    def _swap(self, i, j):
        # Swap elements in heap array
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        # Update hash map index tracking
        self.position_map[self.heap[i].plot_id] = i
        self.position_map[self.heap[j].plot_id] = j

    def _sift_up(self, idx):
        parent = (idx - 1) // 2
        while idx > 0 and self.heap[idx].water_stress_score > self.heap[parent].water_stress_score:
            self._swap(idx, parent)
            idx = parent
            parent = (idx - 1) // 2

    def _sift_down(self, idx):
        max_idx = idx
        size = len(self.heap)
        
        while True:
            left = 2 * idx + 1
            right = 2 * idx + 2

            if left < size and self.heap[left].water_stress_score > self.heap[max_idx].water_stress_score:
                max_idx = left
            if right < size and self.heap[right].water_stress_score > self.heap[max_idx].water_stress_score:
                max_idx = right

            if max_idx != idx:
                self._swap(idx, max_idx)
                idx = max_idx
            else:
                break

    def insert_or_update(self, node: PlotNode):
        """Inserts a new plot or updates stress score of an existing plot in O(log N)."""
        if node.plot_id in self.position_map:
            idx = self.position_map[node.plot_id]
            old_score = self.heap[idx].water_stress_score
            self.heap[idx] = node  # Update node payload
            
            # Re-heapify based on score shift
            if node.water_stress_score > old_score:
                self._sift_up(idx)
            else:
                self._sift_down(idx)
        else:
            # New plot insertion
            idx = len(self.heap)
            self.heap.append(node)
            self.position_map[node.plot_id] = idx
            self._sift_up(idx)

    def peek_max(self):
        """O(1) access to highest water-stress farm plot."""
        if not self.heap:
            return None
        return self.heap[0]

    def extract_max(self):
        """Extracts and returns the maximum stress plot in O(log N)."""
        if not self.heap:
            return None
        
        max_node = self.heap[0]
        last_node = self.heap.pop()
        del self.position_map[max_node.plot_id]

        if self.heap:
            self.heap[0] = last_node
            self.position_map[last_node.plot_id] = 0
            self._sift_down(0)

        return max_node

    def get_top_k(self, k=10):
        """Returns top K critical plots sorted without altering heap state."""
        return [node.to_dict() for node in sorted(self.heap, key=lambda x: x.water_stress_score, reverse=True)[:k]]

