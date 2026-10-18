// Copyright Epic Games, Inc. All Rights Reserved.

#include "IPickupable.h"

#include "GameFramework/Actor.h"
#include "LyraInventoryManagerComponent.h"
#include "UObject/ScriptInterface.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(IPickupable)

class UActorComponent;

UPickupableStatics::UPickupableStatics()
	: Super(FObjectInitializer::Get())
{
}

TScriptInterface<IPickupable> UPickupableStatics::GetFirstPickupableFromActor(AActor* Actor)
{
	// BENCHMARK(interaction): implement the behavior required by Benchmarks/interaction/TASK.md.
	return TScriptInterface<IPickupable>();
}

void UPickupableStatics::AddPickupToInventory(ULyraInventoryManagerComponent* InventoryComponent, TScriptInterface<IPickupable> Pickup)
{
	// BENCHMARK(interaction): implement the behavior required by Benchmarks/interaction/TASK.md.
}
