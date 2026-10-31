#version 450

layout(local_size_x = 128, local_size_y = 1, local_size_z = 1) in;

layout(std430, binding = 0) buffer StressData {
    uint data[];
};

void main() {
    uint i = gl_GlobalInvocationID.x;
    uint x = data[i] ^ (i * 0x9e3779b9u);

    for (uint r = 0u; r < 192u; ++r) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        x = x * 1664525u + 1013904223u;
        x ^= (r + 1u) * 0x85ebca6bu;
    }

    data[i] = x;
}
