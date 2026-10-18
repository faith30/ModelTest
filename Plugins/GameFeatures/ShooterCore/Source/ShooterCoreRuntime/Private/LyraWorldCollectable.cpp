// Copyright Epic Games, Inc. All Rights Reserved.

#include "LyraWorldCollectable.h"

#include "Async/TaskGraphInterfaces.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraWorldCollectable)

struct FInteractionQuery;

ALyraWorldCollectable::ALyraWorldCollectable()
{
}

void ALyraWorldCollectable::GatherInteractionOptions(const FInteractionQuery& InteractQuery, FInteractionOptionBuilder& InteractionBuilder)
{
	// BENCHMARK(interaction): implement the behavior required by Benchmarks/interaction/TASK.md.
}

FInventoryPickup ALyraWorldCollectable::GetPickupInventory() const
{
	// BENCHMARK(interaction): implement the behavior required by Benchmarks/interaction/TASK.md.
	return FInventoryPickup();
}
